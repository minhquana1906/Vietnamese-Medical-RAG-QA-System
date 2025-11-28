from typing import Any, Dict, List, Optional

from loguru import logger
from ..configs.setup import get_backend_settings
from ..configs.logging_config import get_rag_logger

settings = get_backend_settings()
rag_log = get_rag_logger()


def reciprocal_rank_fusion(
    search_results_list: List[List[Dict[str, Any]]],
    k: int = 60,
    score_key: str = "score",
    id_key: str = "chunk_id",
) -> List[Dict[str, Any]]:
    rrf_scores: Dict[Any, float] = {}
    doc_map: Dict[Any, Dict[str, Any]] = {}

    for results in search_results_list:
        for rank, doc in enumerate(results, start=1):
            doc_id = doc.get(id_key)
            if doc_id is None:
                continue

            rrf_contribution = 1.0 / (k + rank)

            if doc_id in rrf_scores:
                rrf_scores[doc_id] += rrf_contribution
            else:
                rrf_scores[doc_id] = rrf_contribution
                doc_map[doc_id] = doc

    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    fused_results = []
    for doc_id, rrf_score in sorted_docs:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = rrf_score
        doc["search_type"] = "hybrid"
        fused_results.append(doc)

    return fused_results


def hybrid_search(
    query: str,
    vector_search_fn,
    keyword_search_fn,
    top_k: int = settings.top_k,
    rrf_k: int = 60,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """Perform hybrid search combining vector and keyword search with RRF fusion."""
    import time

    start_time = time.time()

    # Check cache first
    cache_hit = False
    if use_cache:
        from ..core.cache import cache_search_results, get_search_results

        cached_results = get_search_results(query, search_type="hybrid")
        if cached_results:
            cache_hit = True
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
                pass
            # Log retrieval with cache hit
            rag_log.log_retrieval(
                vector_count=0,
                keyword_count=0,
                fused_count=len(cached_results[:top_k]),
                cache_hit=True,
            )
            return cached_results[:top_k]

    # Perform vector search
    vector_results = vector_search_fn(query, top_k=top_k * 2)

    # Perform keyword search
    keyword_results = keyword_search_fn(query, top_k=top_k * 2)

    # Apply RRF fusion
    fused_results = reciprocal_rank_fusion(
        search_results_list=[vector_results, keyword_results],
        k=rrf_k,
        score_key="score",
        id_key="chunk_id",
    )

    final_results = fused_results[:top_k]

    # Cache results
    if use_cache:
        from ..core.cache import cache_search_results

        cache_search_results(query, final_results, search_type="hybrid")

    # Metrics
    try:
        from .metrics import rag_search_requests_total, rag_search_duration_seconds

        rag_search_requests_total.labels(search_type="hybrid").inc()
        rag_search_duration_seconds.labels(search_type="hybrid").observe(
            time.time() - start_time
        )
    except ImportError:
        pass

    # Log retrieval results
    rag_log.log_retrieval(
        vector_count=len(vector_results),
        keyword_count=len(keyword_results),
        fused_count=len(final_results),
        cache_hit=False,
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
    vector_results = vector_search_fn(
        query,
        top_k=top_k * 2,
        doc_type_filter=doc_type_filter,
        source_filter=source_filter,
    )

    keyword_results = keyword_search_fn(
        query,
        top_k=top_k * 2,
        doc_type_filter=doc_type_filter,
        source_filter=source_filter,
    )

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
