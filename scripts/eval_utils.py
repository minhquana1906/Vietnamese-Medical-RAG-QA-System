"""
Evaluation utilities for RAG pipeline.

This module provides functions to compute:
1. Performance metrics: Latency (p50, p95), token usage
2. Traditional retrieval metrics: Recall@K, Precision@K, nDCG@K, MRR
3. Report formatting
"""

from __future__ import annotations

import numpy as np
from loguru import logger


def compute_text_overlap(text1: str, text2: str, threshold: float = 0.3) -> bool:
    """
    Check if two texts have significant overlap using token-based Jaccard similarity.

    Args:
        text1: First text
        text2: Second text
        threshold: Minimum Jaccard similarity to consider as overlap

    Returns:
        True if texts have significant overlap
    """
    if not text1 or not text2:
        return False

    # Simple tokenization (split by whitespace and punctuation)
    tokens1 = set(text1.lower().split())
    tokens2 = set(text2.lower().split())

    if not tokens1 or not tokens2:
        return False

    # Jaccard similarity
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    similarity = intersection / union if union > 0 else 0
    return similarity >= threshold


def compute_retrieval_metrics(
    predictions: list[dict],
    ground_truths: list[dict],
    k_values: list[int] | None = None,
    overlap_threshold: float = 0.3,
) -> dict[str, float]:
    """
    Compute traditional retrieval metrics using text overlap.

    Since we don't have explicit document IDs matching between ground_truth_contexts
    and retrieved_contexts, we use text overlap to determine relevance.

    Args:
        predictions: List of dicts with 'retrieved_contexts' (list of strings)
        ground_truths: List of dicts with 'ground_truth_contexts' (list of strings)
        k_values: List of K values for Recall@K, Precision@K (default: [1, 3, 5, 10])
        overlap_threshold: Jaccard similarity threshold for considering a match

    Returns:
        Dictionary with:
        - recall@k: Proportion of relevant docs retrieved at top-K
        - precision@k: Proportion of retrieved docs that are relevant at top-K
        - mrr: Mean Reciprocal Rank
        - ndcg@k: Normalized Discounted Cumulative Gain at top-K
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    metrics = {}

    # Initialize accumulators
    recall_at_k = {k: [] for k in k_values}
    precision_at_k = {k: [] for k in k_values}
    reciprocal_ranks = []
    ndcg_at_k = {k: [] for k in k_values}

    for pred, gt in zip(predictions, ground_truths):
        retrieved = pred.get("retrieved_contexts", [])
        ground_truth = gt.get("ground_truth_contexts", [])

        if not ground_truth:
            # Skip samples without ground truth contexts
            continue

        # Find which retrieved docs match ground truth (using text overlap)
        relevance_scores = []
        for ret_ctx in retrieved:
            is_relevant = any(
                compute_text_overlap(ret_ctx, gt_ctx, overlap_threshold)
                for gt_ctx in ground_truth
            )
            relevance_scores.append(1.0 if is_relevant else 0.0)

        # Compute metrics for each K
        for k in k_values:
            top_k_relevance = relevance_scores[:k]

            # Recall@K: How many relevant docs are in top-K?
            relevant_in_top_k = sum(top_k_relevance)
            recall = relevant_in_top_k / len(ground_truth) if ground_truth else 0
            recall_at_k[k].append(recall)

            # Precision@K: What proportion of top-K are relevant?
            precision = relevant_in_top_k / k if k > 0 else 0
            precision_at_k[k].append(precision)

            # nDCG@K
            dcg = sum(
                rel / np.log2(i + 2)  # i+2 because log2(1) = 0
                for i, rel in enumerate(top_k_relevance)
            )
            # Ideal DCG (all relevant docs at top)
            ideal_relevance = sorted(relevance_scores, reverse=True)[:k]
            idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_relevance))
            ndcg = dcg / idcg if idcg > 0 else 0
            ndcg_at_k[k].append(ndcg)

        # MRR: Reciprocal of rank of first relevant doc
        first_relevant_rank = None
        for i, rel in enumerate(relevance_scores):
            if rel > 0:
                first_relevant_rank = i + 1  # 1-indexed
                break
        rr = 1.0 / first_relevant_rank if first_relevant_rank else 0
        reciprocal_ranks.append(rr)

    # Aggregate metrics
    for k in k_values:
        if recall_at_k[k]:
            metrics[f"recall@{k}"] = float(np.mean(recall_at_k[k]))
            metrics[f"precision@{k}"] = float(np.mean(precision_at_k[k]))
            metrics[f"ndcg@{k}"] = float(np.mean(ndcg_at_k[k]))

    if reciprocal_ranks:
        metrics["mrr"] = float(np.mean(reciprocal_ranks))

    logger.info(f"Computed retrieval metrics for {len(reciprocal_ranks)} samples")
    return metrics


def compute_performance_metrics(
    timestamps: list[dict], token_counts: list[dict]
) -> dict[str, float]:
    """
    Compute performance metrics from timestamps and token usage.

    Args:
        timestamps: List of dicts with stage latencies (in seconds):
            - 'end_to_end': Total latency
            - 'embedding': Embedding generation time
            - 'retrieval': Search time
            - 'reranking': Reranking time
            - 'generation': LLM generation time
        token_counts: List of dicts with token usage:
            - 'input_tokens': Number of input tokens
            - 'output_tokens': Number of output tokens
            - 'total_tokens': Total tokens

    Returns:
        Dictionary of performance metrics:
            - p50_latency_ms: Median end-to-end latency
            - p95_latency_ms: 95th percentile latency
            - avg_*_latency_ms: Average latency for each stage
            - avg_total_tokens: Average total tokens per query
    """
    metrics = {}

    if timestamps:
        # Extract latencies (convert to milliseconds)
        end_to_end_latencies = [t.get("end_to_end", 0) * 1000 for t in timestamps]
        embedding_latencies = [t.get("embedding", 0) * 1000 for t in timestamps]
        retrieval_latencies = [t.get("retrieval", 0) * 1000 for t in timestamps]
        reranking_latencies = [t.get("reranking", 0) * 1000 for t in timestamps]
        generation_latencies = [t.get("generation", 0) * 1000 for t in timestamps]

        # Compute percentiles
        metrics["p50_latency_ms"] = np.percentile(end_to_end_latencies, 50)
        metrics["p95_latency_ms"] = np.percentile(end_to_end_latencies, 95)

        # Compute averages
        metrics["avg_end_to_end_latency_ms"] = np.mean(end_to_end_latencies)
        metrics["avg_embedding_latency_ms"] = np.mean(embedding_latencies)
        metrics["avg_retrieval_latency_ms"] = np.mean(retrieval_latencies)
        metrics["avg_reranking_latency_ms"] = np.mean(reranking_latencies)
        metrics["avg_generation_latency_ms"] = np.mean(generation_latencies)

    if token_counts:
        # Compute average token usage
        total_tokens = [tc.get("total_tokens", 0) for tc in token_counts]
        input_tokens = [tc.get("input_tokens", 0) for tc in token_counts]
        output_tokens = [tc.get("output_tokens", 0) for tc in token_counts]

        metrics["avg_total_tokens"] = np.mean(total_tokens)
        metrics["avg_input_tokens"] = np.mean(input_tokens)
        metrics["avg_output_tokens"] = np.mean(output_tokens)

    return metrics


def format_eval_report(metrics_dict: dict[str, float]) -> str:
    """
    Format evaluation metrics into a markdown report.

    Args:
        metrics_dict: Dictionary of metric names and values

    Returns:
        Markdown formatted report string
    """
    # Group metrics by category
    ragas_retrieval = {
        k: v
        for k, v in metrics_dict.items()
        if k in ["context_recall", "context_precision"]
    }
    ragas_generation = {
        k: v
        for k, v in metrics_dict.items()
        if k in ["faithfulness", "answer_relevancy", "factual_correctness"]
    }
    traditional_retrieval = {
        k: v
        for k, v in metrics_dict.items()
        if k.startswith("recall@")
        or k.startswith("precision@")
        or k.startswith("ndcg@")
        or k == "mrr"
    }
    performance_metrics = {
        k: v for k, v in metrics_dict.items() if "latency" in k or "tokens" in k
    }

    report = "# RAG Evaluation Report\n\n"
    report += f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    # Ragas Retrieval Metrics
    if ragas_retrieval:
        report += "## Ragas Retrieval Metrics\n\n"
        report += "| Metric | Score |\n"
        report += "|--------|-------|\n"
        for metric, score in sorted(ragas_retrieval.items()):
            report += f"| {metric} | {score:.4f} |\n"
        report += "\n"

    # Ragas Generation Metrics
    if ragas_generation:
        report += "## Ragas Generation Quality Metrics\n\n"
        report += "| Metric | Score |\n"
        report += "|--------|-------|\n"
        for metric, score in sorted(ragas_generation.items()):
            report += f"| {metric} | {score:.4f} |\n"
        report += "\n"

    # Traditional Retrieval Metrics
    if traditional_retrieval:
        report += "## Traditional Retrieval Metrics\n\n"
        report += "| Metric | Score |\n"
        report += "|--------|-------|\n"
        for metric, score in sorted(traditional_retrieval.items()):
            report += f"| {metric} | {score:.4f} |\n"
        report += "\n"

    # Performance Metrics
    if performance_metrics:
        report += "## Performance Metrics\n\n"
        report += "| Metric | Value |\n"
        report += "|--------|-------|\n"
        for metric, value in sorted(performance_metrics.items()):
            if "latency" in metric:
                report += f"| {metric} | {value:.2f} ms |\n"
            else:
                report += f"| {metric} | {value:.2f} |\n"
        report += "\n"

    return report
