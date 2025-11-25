# Plan: Comprehensive RAG Evaluation System với DeepEval

Xây dựng evaluation framework đầy đủ để đo lường chất lượng RAG pipeline trên 3 khía cạnh: Retrieval quality, Generation quality, và Performance. Sử dụng **DeepEval** làm công cụ chính (tích hợp tốt với LlamaIndex đã có sẵn) để tạo metrics chân thực cho báo cáo project.

## Steps

1. **Install evaluation dependencies**: Thêm `deepeval>=0.21.73` vào `backend/pyproject.toml`, run `uv sync --all-groups` để cài đặt. Verify DeepEval CLI: `deepeval --version`.

2. **Create evaluation test dataset**: Tạo `data/eval_dataset.jsonl` với 50-100 Vietnamese medical Q&A pairs. Mỗi entry gồm: `{"question": "...", "expected_answer": "...", "ground_truth_contexts": ["...", "..."]}`. Sample từ `vietnamese_medical_corpus_dataset` đã indexed.

3. **Implement main evaluation script**: Tạo `backend/scripts/evaluate_rag.py` với CLI args (`--dataset`, `--output`, `--metrics`). Load dataset → call existing RAG pipeline `message_handler_task` → collect predictions/timestamps → compute metrics → generate markdown report.

4. **Implement retrieval metrics module**: Tạo `backend/scripts/eval_utils.py` với functions `compute_retrieval_metrics()` để tính **Recall@K** (K=1,3,5,10), **nDCG@K**, **MRR**, **Precision@K** từ retrieved chunks và ground truth contexts.

5. **Integrate DeepEval generation metrics**: Trong `evaluate_rag.py`, sử dụng DeepEval metrics: `FaithfulnessMetric` (check hallucinations), `AnswerRelevancyMetric` (semantic relevance), `ContextualRelevancyMetric` (retrieval quality), `CorrectnessMetric` (vs ground truth). Configure với LLM judge: Qwen3-4B từ `models.yaml`.

6. **Implement performance metrics tracking**: Thêm timestamp tracking vào `evaluate_rag.py`: measure end-to-end latency, embedding latency (từ `embedding.py`), retrieval latency (từ `hybrid_search.py`), reranking latency (từ `rerank.py`), generation latency (từ `brain.py`), và token usage.

7. **Run evaluation suite và verify thresholds**: Execute `python backend/scripts/evaluate_rag.py --dataset data/eval_dataset.jsonl --output data/eval_results/`. Check results meet thresholds: Retrieval (Recall@5≥0.70, nDCG@5≥0.65, MRR≥0.60), Generation (Faithfulness≥0.80, Answer Relevance≥0.75, Correctness≥0.70), Performance (p95≤5000ms, p50≤3000ms). Generate markdown report `data/eval_results/evaluation_report.md`.

## Further Considerations

1. **Evaluation Dataset Quality**: Nên tạo dataset như thế nào? Hybrid (50 manual + 150 generated).

2. **LLM Judge Selection**: Dùng model nào làm judge cho generation metrics? Bạn nên tạo hàm cho lựa chọn judge model (Qwen3-4B local / GPT-4o / Dual validation) trong `evaluate_rag.py` để dễ thay đổi sau này.

3. **Metric Prioritization**: Focus vào metrics nào trước? Phased approach (retrieval → generation → performance).
