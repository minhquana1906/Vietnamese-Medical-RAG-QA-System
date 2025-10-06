import cohere
import yaml
from loguru import logger

from .config import get_backend_settings

settings = get_backend_settings()


def get_cohere_client():
    try:
        api_key = settings.cohere_api_key
        if not api_key:
            raise ValueError("COHERE_API_KEY environment variable not set.")
        client = cohere.Client(api_key)
        return client
    except Exception as e:
        logger.error(f"Error initializing Cohere client: {e}")
        raise


def rerank_documents(query, documents, model=settings.cohere_rerank_model, top_n=5):
    """
    Rerank documents using Cohere rerank API.

    Note: Keeps rerank results (CRITICAL for quality monitoring).
    Format optimized for readability.
    """
    try:
        client = get_cohere_client()
        yaml_docs = [yaml.dump(doc, sort_keys=False) for doc in documents]

        reranked_documents = client.rerank(
            query=query, documents=yaml_docs, model=model, top_n=top_n
        ).results

        # Log reranked results in compact format
        rerank_summary = ", ".join([
            f"#{rank} (score={doc.relevance_score:.3f})"
            for rank, doc in enumerate(reranked_documents, start=1)
        ])
        logger.info(f"Reranked {len(reranked_documents)} docs: {rerank_summary}")

        return reranked_documents
    except Exception as e:
        logger.error(f"Error reranking documents: {e}")
        raise
