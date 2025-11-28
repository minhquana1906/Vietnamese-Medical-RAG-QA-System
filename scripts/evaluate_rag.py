#!/usr/bin/env python3
"""
RAG Pipeline Evaluation Script with Ragas v0.3.9

Comprehensive evaluation using Ragas framework.
Evaluates 3 aspects:
1. Retrieval Quality: Context Recall, Context Precision
2. Generation Quality: Faithfulness, Answer Relevancy, Factual Correctness
3. Performance: Latency (p50, p95), Token usage

Key Features:
- Proper embedding configuration for semantic metrics
- Traditional retrieval metrics (Recall@K, nDCG@K, MRR, Precision@K)
- Ground truth context validation
- Detailed per-sample analysis
- Vietnamese language adaptation for metrics

Usage:
    uv run scripts/evaluate_rag.py \
        --dataset data/eval_dataset.jsonl \
        --output data/eval_results/ \
        --judge-model deepseek-chat \
        --top-k 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from langchain_openai import ChatOpenAI
from loguru import logger
from ragas import EvaluationDataset, evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (AnswerRelevancy, ContextPrecision,
                           FactualCorrectness, Faithfulness, LLMContextRecall)

# Import RAG pipeline components
from backend.src.configs.setup import get_backend_settings
from backend.src.core.hybrid_search import hybrid_search
from backend.src.core.vectorize import search_vectors_for_hybrid
from backend.src.services.brain import qwen3_chat_complete
from backend.src.services.elasticsearch import get_elasticsearch_client
from backend.src.services.embedding import get_embedding_service
from backend.src.services.rerank import get_qwen3_reranker
# Import utilities
from scripts.eval_utils import (compute_performance_metrics,
                                compute_retrieval_metrics, format_eval_report)

settings = get_backend_settings()


# --- Custom Embeddings for Ragas ---
class Qwen3EmbeddingsForRagas:
    """
    Custom embedding wrapper for Ragas using Qwen3-Embedding-0.6B.
    This ensures evaluation uses the same embeddings as production.

    Implements Ragas BaseRagasEmbeddings interface:
    - embed_query: For queries (with instruction prefix)
    - embed_documents: For documents (batch, no instruction)
    - embed_text/embed_texts: Legacy methods
    """

    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.task_instruction = (
            "Given a text, generate an embedding for semantic similarity comparison"
        )

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query with instruction prefix (Ragas interface)."""
        return self.embedding_service.embed_query(
            text, use_cache=False, task_instruction=self.task_instruction
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents without instruction (Ragas interface)."""
        return self.embedding_service.embed_batch_documents(texts)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text (legacy Ragas method)."""
        return self.embed_query(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts (legacy Ragas method)."""
        return self.embed_documents(texts)


# --- RAG System Prompt ---
RAG_SYSTEM_PROMPT = """Bạn là trợ lý y tế AI chuyên nghiệp. Hãy trả lời câu hỏi dựa trên tài liệu được cung cấp."""


def load_eval_dataset(dataset_path: str) -> list[dict]:
    """
    Load evaluation dataset from JSONL file.

    Expected format:
    {
        "question": "...",
        "expected_answer": "...",
        "ground_truth_contexts": ["...", "..."]
    }
    """
    dataset = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                # Validate required fields
                if "question" in item and "expected_answer" in item:
                    # Ensure ground_truth_contexts is a list
                    if "ground_truth_contexts" not in item:
                        item["ground_truth_contexts"] = []
                    elif isinstance(item["ground_truth_contexts"], str):
                        item["ground_truth_contexts"] = [item["ground_truth_contexts"]]
                    dataset.append(item)

    logger.info(f"Loaded {len(dataset)} test cases from {dataset_path}")
    return dataset


def run_rag_pipeline(
    query: str, top_k: int = 5
) -> tuple[str, list[str], dict[str, float], list[dict]]:
    """
    Run RAG pipeline and collect intermediate results.

    Returns:
        tuple: (answer, retrieved_contexts, timestamps, raw_search_results)
    """
    timestamps = {}
    embedding_service = get_embedding_service()

    # Task instruction for medical retrieval
    embedding_instruction = (
        "Given a medical question, retrieve relevant medical knowledge passages "
        "that provide accurate information to answer the question"
    )

    # 1. Embedding
    start_time = time.time()
    query_embedding = embedding_service.embed_query(
        query,
        use_cache=False,
        task_instruction=embedding_instruction,
    )
    timestamps["embedding"] = time.time() - start_time

    # 2. Hybrid Search (Vector + Keyword with RRF)
    def vector_search_fn(query_text, top_k, doc_type_filter=None, source_filter=None):
        return search_vectors_for_hybrid(
            query_vector=query_embedding,
            top_k=top_k,
            collection_name=settings.default_collection_name,
            doc_type_filter=doc_type_filter,
            source_filter=source_filter,
        )

    def keyword_search_fn(query_text, top_k, doc_type_filter=None, source_filter=None):
        es_client = get_elasticsearch_client()
        return es_client.search_bm25(
            query=query_text,
            top_k=top_k,
            doc_type_filter=doc_type_filter,
            source_filter=source_filter,
        )

    start_time = time.time()
    search_results = hybrid_search(
        query=query,
        vector_search_fn=vector_search_fn,
        keyword_search_fn=keyword_search_fn,
        top_k=20,
        use_cache=False,
    )
    timestamps["retrieval"] = time.time() - start_time

    # 3. Reranking
    start_time = time.time()
    documents_for_rerank = [
        {"title": doc.get("title", ""), "content": doc.get("content", "")}
        for doc in search_results
    ]

    rerank_instruction = (
        "Given a medical question, determine if the passage contains "
        "relevant information to answer the question accurately"
    )

    reranker = get_qwen3_reranker()
    reranked_results, _ = reranker.rerank(
        query=query,
        documents=documents_for_rerank,
        top_n=top_k,
        task_instruction=rerank_instruction,
    )
    timestamps["reranking"] = time.time() - start_time

    # Extract contexts
    retrieved_contexts = []
    for result in reranked_results[:top_k]:
        if result.get("document") and result["document"].get("content"):
            retrieved_contexts.append(result["document"]["content"])

    # 4. Generation
    context_str = "\n\n".join(
        [f"[{i+1}] {ctx}" for i, ctx in enumerate(retrieved_contexts)]
    )

    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""Dựa vào các tài liệu sau, hãy trả lời câu hỏi của người dùng.

Tài liệu tham khảo:
{context_str}

Câu hỏi: {query}

Trả lời bằng câu hỏi bằng tiếng Việt:""",
        },
    ]

    start_time = time.time()
    response = qwen3_chat_complete(messages, temperature=0.7, max_tokens=1536)
    timestamps["generation"] = time.time() - start_time
    timestamps["end_to_end"] = sum(timestamps.values())

    return response, retrieved_contexts, timestamps, reranked_results


def create_ragas_dataset(
    predictions: list[dict], ground_truths: list[dict]
) -> EvaluationDataset:
    """
    Create Ragas EvaluationDataset from predictions and ground truths.

    Ragas v0.3.9 schema:
    - user_input: The user query
    - response: The generated answer
    - reference: The ground truth answer
    - retrieved_contexts: List of retrieved contexts
    - reference_contexts: List of ground truth contexts (for context recall)
    """
    dataset_list = []
    for pred, gt in zip(predictions, ground_truths):
        dataset_list.append(
            {
                "user_input": gt["question"],
                "response": pred["answer"],
                "reference": gt["expected_answer"],
                "retrieved_contexts": pred["retrieved_contexts"],
                "reference_contexts": gt.get("ground_truth_contexts", []),
            }
        )

    return EvaluationDataset.from_list(dataset_list)


def setup_llm_judge(judge_model: str) -> tuple[object, object | None]:
    """
    Setup LLM judge and embeddings for Ragas evaluation.

    Returns:
        tuple: (evaluator_llm, evaluator_embeddings)
    """
    if judge_model == "deepseek-chat":
        base_url = "https://api.deepseek.com"
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set.")
    elif judge_model in ["gpt-4o", "gpt-4o-mini"]:
        base_url = "https://api.openai.com/v1"
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
    else:
        raise ValueError(f"Unsupported judge model: {judge_model}")

    llm = ChatOpenAI(
        model=judge_model, base_url=base_url, api_key=api_key, temperature=0
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        evaluator_llm = LangchainLLMWrapper(llm)

    # Use Qwen3 embeddings for semantic metrics
    evaluator_embeddings = Qwen3EmbeddingsForRagas()

    return evaluator_llm, evaluator_embeddings


async def adapt_metrics_to_vietnamese(
    metrics: list, llm: object, language: str = "vietnamese"
) -> list:
    """
    Adapt evaluation metrics to Vietnamese language.
    This ensures LLM-based metrics properly handle Vietnamese text.

    According to Ragas docs, this translates few-shot examples to target language
    while keeping instructions in English.
    """
    logger.info(f"Adapting {len(metrics)} metrics to {language}...")
    adapted_metrics = []

    for metric in metrics:
        try:
            adapted_prompts = await metric.adapt_prompts(language=language, llm=llm)
            metric.set_prompts(**adapted_prompts)
            logger.debug(f"Adapted {metric.__class__.__name__} to {language}")
        except Exception as e:
            logger.warning(
                f"Failed to adapt {metric.__class__.__name__}: {e}. Using default prompts."
            )
        adapted_metrics.append(metric)

    logger.success(f"Successfully adapted metrics to {language}")
    return adapted_metrics


async def run_evaluation_async(
    dataset_path: str,
    output_dir: str,
    judge_model: str = "deepseek-chat",
    top_k: int = 5,
    k_values: list[int] | None = None,
) -> dict:
    """
    Run complete RAG evaluation pipeline using Ragas v0.3.9.

    Evaluates:
    1. Ragas metrics (LLM-based): Context Recall, Context Precision,
       Faithfulness, Answer Relevancy, Factual Correctness
    2. Traditional retrieval metrics: Recall@K, Precision@K, nDCG@K, MRR
    3. Performance metrics: Latency percentiles, stage breakdown
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Load dataset
    dataset = load_eval_dataset(dataset_path)

    # Collect predictions
    predictions = []
    timestamps_list = []

    logger.info("Running RAG pipeline for all test cases...")
    for i, item in enumerate(dataset):
        logger.info(
            f"Processing query {i+1}/{len(dataset)}: {item['question'][:50]}..."
        )

        try:
            answer, retrieved_contexts, timestamps, raw_results = run_rag_pipeline(
                item["question"], top_k=top_k
            )

            predictions.append(
                {
                    "query": item["question"],
                    "answer": answer,
                    "retrieved_contexts": retrieved_contexts,
                    "raw_results": raw_results,
                }
            )
            timestamps_list.append(timestamps)

        except Exception as e:
            logger.error(f"Error processing query {i+1}: {e}")
            predictions.append(
                {
                    "query": item["question"],
                    "answer": "",
                    "retrieved_contexts": [],
                    "raw_results": [],
                }
            )
            timestamps_list.append(
                {
                    "embedding": 0,
                    "retrieval": 0,
                    "reranking": 0,
                    "generation": 0,
                    "end_to_end": 0,
                }
            )

    # Save predictions
    predictions_file = os.path.join(output_dir, f"predictions_{timestamp}.jsonl")
    with open(predictions_file, "w", encoding="utf-8") as f:
        for pred in predictions:
            # Remove raw_results for cleaner output
            output_pred = {k: v for k, v in pred.items() if k != "raw_results"}
            f.write(json.dumps(output_pred, ensure_ascii=False) + "\n")
    logger.info(f"Saved predictions to {predictions_file}")

    # Create Ragas dataset
    logger.info("Creating Ragas evaluation dataset...")
    ragas_dataset = create_ragas_dataset(predictions, dataset)

    # Setup LLM judge
    logger.info(f"Initializing LLM judge: {judge_model}")
    evaluator_llm, evaluator_embeddings = setup_llm_judge(judge_model)

    # Define Ragas metrics
    # Note: strictness=1 for AnswerRelevancy because Deepseek API only supports n=1
    # (default strictness=3 would request n=3 completions which Deepseek doesn't support)
    logger.info("Initializing Ragas metrics...")
    metrics = [
        LLMContextRecall(llm=evaluator_llm),  # Requires reference_contexts
        ContextPrecision(llm=evaluator_llm),
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(
            llm=evaluator_llm, embeddings=evaluator_embeddings, strictness=1
        ),
        FactualCorrectness(llm=evaluator_llm),
    ]

    # Adapt metrics to Vietnamese language
    # This translates few-shot examples to Vietnamese for better evaluation
    logger.info("Adapting metrics to Vietnamese...")
    metrics = await adapt_metrics_to_vietnamese(metrics, evaluator_llm, "vietnamese")

    # Run Ragas evaluation
    logger.info("Running Ragas evaluation...")
    try:
        result = evaluate(dataset=ragas_dataset, metrics=metrics, llm=evaluator_llm)
        df = result.to_pandas()

        # Save detailed results
        detail_results_file = os.path.join(
            output_dir, f"detail_results_{timestamp}.jsonl"
        )
        df.to_json(detail_results_file, orient="records", lines=True, force_ascii=False)
        logger.info(f"Saved detailed Ragas results to {detail_results_file}")

    except Exception as e:
        logger.error(f"Ragas evaluation failed: {e}")
        df = pd.DataFrame()

    # Extract Ragas metrics
    ragas_metrics = {}
    metric_names = [
        "context_recall",
        "context_precision",
        "faithfulness",
        "answer_relevancy",
        "factual_correctness",
    ]

    for metric_name in metric_names:
        if metric_name in df.columns:
            values = pd.to_numeric(df[metric_name], errors="coerce").dropna()
            if len(values) > 0:
                ragas_metrics[metric_name] = float(values.mean())

    # Compute traditional retrieval metrics
    logger.info("Computing traditional retrieval metrics...")
    retrieval_metrics = compute_retrieval_metrics(
        predictions=predictions,
        ground_truths=dataset,
        k_values=k_values,
    )

    # Compute performance metrics
    performance_metrics = compute_performance_metrics(timestamps_list, [])

    # Combine all metrics
    all_metrics = {
        **ragas_metrics,
        **retrieval_metrics,
        **performance_metrics,
    }

    # Save metrics
    metrics_file = os.path.join(output_dir, f"metrics_{timestamp}.json")
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved metrics to {metrics_file}")

    # Generate report
    report = format_eval_report(all_metrics)

    # Add threshold validation
    report += "\n## Threshold Validation\n\n"
    report += "| Metric | Target | Actual | Status |\n"
    report += "|--------|--------|--------|--------|\n"

    thresholds = {
        "context_recall": 0.70,
        "context_precision": 0.65,
        "faithfulness": 0.80,
        "answer_relevancy": 0.75,
        "factual_correctness": 0.70,
        "recall@5": 0.70,
        "p95_latency_ms": 10000,
        "p50_latency_ms": 5000,
    }

    for metric, threshold in thresholds.items():
        if metric in all_metrics:
            actual = all_metrics[metric]
            if "latency" in metric:
                status = "✅ PASS" if actual <= threshold else "❌ FAIL"
            else:
                status = "✅ PASS" if actual >= threshold else "❌ FAIL"
            report += f"| {metric} | {threshold} | {actual:.4f} | {status} |\n"

    # Save report
    report_file = os.path.join(output_dir, f"evaluation_report_{timestamp}.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Saved evaluation report to {report_file}")

    return all_metrics


def run_evaluation(
    dataset_path: str,
    output_dir: str,
    judge_model: str = "deepseek-chat",
    top_k: int = 5,
    k_values: list[int] | None = None,
) -> dict:
    """
    Synchronous wrapper for run_evaluation_async.
    """
    return asyncio.run(
        run_evaluation_async(
            dataset_path=dataset_path,
            output_dir=output_dir,
            judge_model=judge_model,
            top_k=top_k,
            k_values=k_values,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate RAG pipeline with Ragas v0.3.9"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="data/eval_dataset.jsonl",
        help="Path to evaluation dataset (JSONL format)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/eval_results/",
        help="Output directory for results",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        choices=["deepseek-chat", "gpt-4o-mini", "gpt-4o"],
        default="deepseek-chat",
        help="LLM judge model for evaluation metrics",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of top documents to retrieve",
    )
    parser.add_argument(
        "--k-values",
        type=int,
        nargs="+",
        default=[1, 3, 5, 10],
        help="K values for Recall@K, Precision@K metrics",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("RAG Pipeline Evaluation with Ragas v0.3.9")
    logger.info("=" * 60)
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Judge Model: {args.judge_model}")
    logger.info(f"Top-K: {args.top_k}")
    logger.info(f"K Values: {args.k_values}")
    logger.info("=" * 60)

    # Run evaluation
    metrics = run_evaluation(
        dataset_path=args.dataset,
        output_dir=args.output,
        judge_model=args.judge_model,
        top_k=args.top_k,
        k_values=args.k_values,
    )

    logger.info("\n" + "=" * 60)
    logger.info("Evaluation Complete!")
    logger.info("=" * 60)
    logger.info(f"Results saved to: {args.output}")

    # Print summary
    logger.info("\nMetrics Summary:")
    for metric, value in sorted(metrics.items()):
        if "latency" in metric:
            logger.info(f"  {metric}: {value:.2f} ms")
        else:
            logger.info(f"  {metric}: {value:.4f}")


if __name__ == "__main__":
    main()
