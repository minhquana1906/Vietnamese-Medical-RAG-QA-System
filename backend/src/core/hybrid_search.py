from typing import Any, Dict, List, Optional

from loguru import logger
from ..configs.setup import get_backend_settings

settings = get_backend_settings()


def reciprocal_rank_fusion(
    search_results_list: List[List[Dict[str, Any]]],
    k: int = 60,
    score_key: str = "score",
    id_key: str = "chunk_id",
) -> List[Dict[str, Any]]:
    rrf_scores: Dict[Any, float] = {}
    doc_map: Dict[Any, Dict[str, Any]] = {}  # Map document ID to full document object

    # Calculate RRF scores
    for results in search_results_list:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc.get(id_key)
            if doc_id is None:
                logger.warning(f"Document missing '{id_key}' field, skipping")
                continue

            # RRF score contribution from this ranked list
            rrf_contribution = 1.0 / (k + rank)

            # Accumulate RRF score
            if doc_id in rrf_scores:
                rrf_scores[doc_id] += rrf_contribution
            else:
                rrf_scores[doc_id] = rrf_contribution
                doc_map[doc_id] = doc  # Store document object

    # Sort by RRF score (descending)
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Build fused result list
    fused_results = []
    for doc_id, rrf_score in sorted_docs:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = rrf_score
        doc["search_type"] = "hybrid"
        fused_results.append(doc)

    logger.debug(
        f"RRF fusion: {len(search_results_list)} result lists → {len(fused_results)} unique documents"
    )
    return fused_results


def hybrid_search(
    query: str,
    vector_search_fn,
    keyword_search_fn,
    top_k: int = settings.top_k,
    rrf_k: int = 60,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """
    Perform hybrid search combining vector and keyword search with RRF fusion.

    Args:
        query: Search query
        vector_search_fn: Function to perform vector search
        keyword_search_fn: Function to perform keyword search
        top_k: Number of results to return
        rrf_k: RRF parameter (default: 60)
        use_cache: Whether to use cache

    Returns:
        List of fused search results
    """
    import time

    start_time = time.time()

    # Check cache first
    if use_cache:
        from ..core.cache import cache_search_results, get_search_results

        cached_results = get_search_results(query, search_type="hybrid")
        if cached_results:
            # Increment metrics for hybrid search (cache hit)
            try:
                from .metrics import (
                    rag_search_requests_total,
                    rag_search_duration_seconds,
                )

                rag_search_requests_total.labels(search_type="hybrid").inc()
                rag_search_duration_seconds.labels(search_type="hybrid").observe(
                    time.time() - start_time
                )
            except ImportError:
                pass  # Metrics not available
            return cached_results[:top_k]

    # Perform vector search
    logger.debug(f"Performing vector search for: {query[:50]}...")
    vector_results = vector_search_fn(
        query, top_k=top_k * 2
    )  # Retrieve more for fusion

    # Perform keyword search
    logger.debug(f"Performing keyword search for: {query[:50]}...")
    keyword_results = keyword_search_fn(
        query, top_k=top_k * 2
    )  # Retrieve more for fusion

    # Apply RRF fusion
    fused_results = reciprocal_rank_fusion(
        search_results_list=[vector_results, keyword_results],
        k=rrf_k,
        score_key="score",
        id_key="chunk_id",
    )

    # Take top-k results
    final_results = fused_results[:top_k]

    # Cache results
    if use_cache:
        from ..core.cache import cache_search_results

        cache_search_results(query, final_results, search_type="hybrid")

    # Increment metrics for hybrid search
    try:
        from .metrics import rag_search_requests_total, rag_search_duration_seconds

        rag_search_requests_total.labels(search_type="hybrid").inc()
        rag_search_duration_seconds.labels(search_type="hybrid").observe(
            time.time() - start_time
        )
    except ImportError:
        pass  # Metrics not available

    logger.info(
        f"Hybrid search returned {len(final_results)} results (vector: {len(vector_results)}, keyword: {len(keyword_results)})"
    )
    return final_results


def hybrid_search_with_filters(
    query: str,
    vector_search_fn,
    keyword_search_fn,
    doc_type_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    top_k: int = settings.top_k,
    rrf_k: int = 60,
) -> List[Dict[str, Any]]:
    # Vector search with filters
    vector_results = vector_search_fn(
        query,
        top_k=top_k * 2,
        doc_type_filter=doc_type_filter,
        source_filter=source_filter,
    )

    # Keyword search with filters
    keyword_results = keyword_search_fn(
        query,
        top_k=top_k * 2,
        doc_type_filter=doc_type_filter,
        source_filter=source_filter,
    )

    # Apply RRF fusion
    fused_results = reciprocal_rank_fusion(
        search_results_list=[vector_results, keyword_results],
        k=rrf_k,
    )

    return fused_results[:top_k]


def analyze_search_overlap(
    vector_results: List[Dict[str, Any]],
    keyword_results: List[Dict[str, Any]],
    id_key: str = "chunk_id",
) -> Dict[str, Any]:
    vector_ids = set(doc.get(id_key) for doc in vector_results if doc.get(id_key))
    keyword_ids = set(doc.get(id_key) for doc in keyword_results if doc.get(id_key))

    overlap_ids = vector_ids & keyword_ids
    union_ids = vector_ids | keyword_ids

    overlap_pct = (len(overlap_ids) / len(union_ids) * 100) if union_ids else 0

    return {
        "vector_count": len(vector_ids),
        "keyword_count": len(keyword_ids),
        "overlap_count": len(overlap_ids),
        "union_count": len(union_ids),
        "overlap_percentage": overlap_pct,
        "vector_only": len(vector_ids - keyword_ids),
        "keyword_only": len(keyword_ids - vector_ids),
    }
