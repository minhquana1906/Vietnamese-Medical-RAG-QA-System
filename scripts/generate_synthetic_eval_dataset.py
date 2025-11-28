import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from llama_index.core import Document, PromptTemplate, SimpleDirectoryReader
from llama_index.core.async_utils import run_jobs
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.deepseek import DeepSeek
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.sql.expression import func

from backend.src.configs.setup import get_backend_settings
from backend.src.database import SessionLocal
from backend.src.models import Document as DBDocument

settings = get_backend_settings()


# --- 1. Define Strict Output Structure ---
class QAOutput(BaseModel):
    question: str = Field(..., description="Câu hỏi y tế rõ ràng bằng tiếng Việt.")
    expected_answer: str = Field(
        ..., description="Câu trả lời chi tiết, chính xác dựa trên ngữ cảnh."
    )


# --- 2. Prompts ---
SYSTEM_PROMPT = """Bạn là chuyên gia y tế AI tạo dữ liệu đánh giá (Golden Dataset).
Nhiệm vụ: Tạo cặp QA từ văn bản y khoa.

QUY TẮC BẤT DI BẤT DỊCH:
1. DATA CLEANING (QUAN TRỌNG): Văn bản đầu vào có thể bị lỗi dính chữ (ví dụ: "thấyngứa") hoặc chứa thông tin quảng cáo. Bạn PHẢI tự động hiểu đúng ngữ nghĩa, sửa lỗi chính tả trong câu trả lời output.
2. NỘI DUNG: Chỉ tập trung vào kiến thức y khoa (triệu chứng, cách chữa, thuốc). TUYỆT ĐỐI KHÔNG tạo câu hỏi về: Hotline, đặt lịch khám, tên bệnh viện, tải app.
3. PHONG CÁCH TRẢ LỜI: Trả lời trực tiếp, chuyên nghiệp như bác sĩ tư vấn. KHÔNG dùng cụm từ "Theo văn bản...", "Đoạn văn đề cập...".
4. FORMAT: JSON chính xác."""

PROMPTS = [
    # Loại 1: Tra cứu (Simple)
    """Hãy tạo 1 câu hỏi dạng "Tra cứu định nghĩa/thông tin". 
    Ví dụ: "Thuốc X dùng để làm gì?", "Triệu chứng Y là gì?".
    Câu trả lời cần ngắn gọn, súc tích.
    Lưu ý: Bỏ qua toàn bộ thông tin về giới thiệu bệnh viện, số điện thoại hay ứng dụng đặt lịch ở cuối văn bản, sửa lại các lỗi chính tả nếu có.""",
    # Loại 2: Hướng dẫn/Lâm sàng (Scenario)
    """Hãy tạo 1 câu hỏi dạng "Tình huống/Hướng dẫn".
    Ví dụ: "Bệnh nhân bị X thì cần lưu ý gì khi dùng thuốc Y?", "Các bước xử lý khi gặp tình trạng Z?".
    Câu trả lời cần đầy đủ các bước hoặc lưu ý quan trọng.
    Lưu ý: Bỏ qua toàn bộ thông tin về giới thiệu bệnh viện, số điện thoại hay ứng dụng đặt lịch ở cuối văn bản, sửa lại các lỗi chính tả nếu có.""",
    # Loại 3: Cảnh báo/Chống chỉ định (Warning)
    """Hãy tạo 1 câu hỏi tập trung vào "Cảnh báo/Tác dụng phụ/Chống chỉ định".
    Ví dụ: "Những ai không nên dùng thuốc này?", "Tương tác thuốc nguy hiểm cần tránh?".
    Câu trả lời cần liệt kê rõ rủi ro.
    Lưu ý: Bỏ qua toàn bộ thông tin về giới thiệu bệnh viện, số điện thoại hay ứng dụng đặt lịch ở cuối văn bản, sửa lại các lỗi chính tả nếu có.""",
]


def load_documents_from_db(limit: Optional[int] = None) -> List[str]:
    if not SessionLocal:
        logger.error("DB Session not found.")
        return []
    db = SessionLocal()
    try:
        query = db.query(DBDocument).order_by(func.random())
        if limit:
            query = query.limit(limit)
        documents = query.all()
        logger.info(f"Loaded {len(documents)} random documents from database")
        return [doc.content for doc in documents if doc.content]
    except Exception as e:
        logger.error(f"Error loading from DB: {e}")
        return []
    finally:
        db.close()


def load_documents_from_directory(doc_dir: str) -> List[str]:
    logger.info(f"Loading documents from directory: {doc_dir}")
    if not os.path.exists(doc_dir):
        logger.error(f"Directory {doc_dir} not found.")
        return []
    reader = SimpleDirectoryReader(doc_dir)
    documents = reader.load_data()
    return [doc.text for doc in documents]


async def generate_single_sample(llm, node, semaphore):
    """Hàm xử lý 1 node (bất đồng bộ)"""
    async with semaphore:  # Giới hạn số luồng
        try:
            prompt_instruction = random.choice(PROMPTS)
            template_str = """
            CONTEXT INFORMATION:
            ---------------------
            {context_str}
            ---------------------
            TASK:
            {instruction_str}
            OUTPUT:
            Trả về đúng định dạng JSON field `question` và `expected_answer`.
            """
            prompt_tmpl = PromptTemplate(template_str)

            # Dùng astructured_predict (có chữ 'a' ở đầu là async)
            qa_result = await llm.astructured_predict(
                QAOutput,
                prompt=prompt_tmpl,
                context_str=node.text,
                instruction_str=prompt_instruction,
            )

            return {
                "question": qa_result.question,
                "expected_answer": qa_result.expected_answer,
                "ground_truth_contexts": [node.text],
            }
        except Exception:
            # logger.warning(f"Failed: {e}")
            return None


async def main():
    parser = argparse.ArgumentParser(
        description="Generate Simple Medical RAG Dataset using DeepSeek"
    )
    parser.add_argument("--num-samples", type=int, default=50)
    parser.add_argument("--output", type=str, default="data/eval_dataset.jsonl")

    # --- Cấu hình Argument cho DeepSeek ---
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-chat",  # Default model là deepseek-chat (V3)
        help="Model to generate data (e.g. deepseek-chat, deepseek-reasoner)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("DEEPSEEK_API_KEY"),
        help="DeepSeek API Key",
    )

    parser.add_argument(
        "--source", type=str, default="database", choices=["database", "directory"]
    )
    parser.add_argument("--doc-dir", type=str)

    args = parser.parse_args()

    if not args.api_key:
        logger.error(
            "Missing API Key. Please set DEEPSEEK_API_KEY environment variable or use --api-key."
        )
        return

    # 1. Load Data
    if args.source == "database":
        docs = load_documents_from_db(limit=350)
    else:
        if not args.doc_dir:
            logger.error("--doc-dir is required for source 'directory'")
            return
        docs = load_documents_from_directory(args.doc_dir)

    if not docs:
        logger.error("No documents found!")
        return

    # 2. Split Nodes
    splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=100)
    llama_docs = [Document(text=d) for d in docs]
    nodes = splitter.get_nodes_from_documents(llama_docs)
    logger.info(f"Prepared {len(nodes)} source nodes.")

    # 3. Setup LLM
    llm = DeepSeek(model=args.model, api_key=args.api_key, temperature=1.5)

    # Cấu hình Batch
    CONCURRENCY_LIMIT = 15
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    # Chọn ngẫu nhiên nodes trước
    selected_nodes = random.choices(nodes, k=args.num_samples)

    # Tạo danh sách tasks
    tasks = [generate_single_sample(llm, node, semaphore) for node in selected_nodes]

    # Chạy tasks và hiện thanh tiến trình
    results = await run_jobs(tasks, show_progress=True, workers=CONCURRENCY_LIMIT)

    # Lọc kết quả lỗi (None) và ghi file
    valid_results = [r for r in results if r is not None]

    with open(args.output, "w", encoding="utf-8") as f:
        for entry in valid_results:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(f"✅ Xong! Đã tạo {len(valid_results)} mẫu.")


if __name__ == "__main__":
    asyncio.run(main())
