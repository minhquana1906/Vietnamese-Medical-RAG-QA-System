from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..configs.setup import get_backend_settings

settings = get_backend_settings()


def get_qdrant_client(host=None, port=None):
    try:
        host = settings.qdrant_host
        port = settings.qdrant_port
        client = QdrantClient(host=host, port=port)
        return client
    except Exception as e:
        logger.error(f"Error initializing Qdrant client: {e}")
        raise


def create_collection(
    collection_name=settings.default_collection_name,
    vector_dimension=settings.vector_dimension,
):
    try:
        client = get_qdrant_client()
        existing_collections = [
            col.name for col in client.get_collections().collections
        ]

        if collection_name not in existing_collections:
            client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_dimension, distance=Distance.COSINE
                ),
            )
            status = f"Collection {collection_name} created with vector dimensions {vector_dimension} successfully"
            logger.info(status)
            return status
        else:
            status = f"Collection {collection_name} already exists"
            logger.info(status)
            return status
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        raise


def upsert_points(points, collection_name=settings.default_collection_name):
    try:
        client = get_qdrant_client()
        point_structs = [
            PointStruct(
                id=point["id"],
                vector=point["embedding"],
                payload=point["metadata"],
            )
            for i, point in enumerate(points)
        ]
        results = client.upsert(collection_name=collection_name, points=point_structs)
        logger.info(
            f"Upserted {len(points)} points to collection {collection_name} successfully"
        )
        return results
    except Exception as e:
        logger.error(f"Error upserting points: {e}")
        raise


def search_vectors(
    query_vector,
    top_k=settings.top_k,
    collection_name=settings.default_collection_name,
):
    try:
        client = get_qdrant_client()
        search_result = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
        )
        results = [
            {
                "id": point.id,
                "score": point.score,
                "title": point.payload.get("title", ""),
                "content": point.payload.get("content", ""),
            }
            for point in search_result
        ]
        logger.info(
            f"Search in collection {collection_name} returned {len(results)} results"
        )
        return results
    except Exception as e:
        logger.error(f"Error searching vectors: {e}")
        raise


def search_vectors_for_hybrid(
    query_vector,
    top_k=settings.top_k,
    collection_name=settings.default_collection_name,
    doc_type_filter=None,
    source_filter=None,
):
    """
    Vector search wrapper for hybrid search integration.

    Returns results in standardized format expected by RRF fusion:
    - chunk_id: Unique chunk identifier
    - document_id: Parent document ID
    - chunk_index: Position in document
    - content: Chunk text content
    - title: Document title
    - score: Similarity score
    - search_type: "vector" marker
    - metadata: Additional metadata

    Args:
        query_vector: Embedding vector for query
        top_k: Number of results to return
        collection_name: Qdrant collection name
        doc_type_filter: Filter by document type (not yet implemented)
        source_filter: Filter by source (not yet implemented)

    Returns:
        List of results in hybrid search format
    """
    try:
        client = get_qdrant_client()

        # TODO: Implement filters when Qdrant payload filtering is added
        search_result = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
        )

        results = [
            {
                "chunk_id": str(point.id),
                "document_id": point.payload.get("doc_id", str(point.id)),
                "chunk_index": point.payload.get("chunk_index", 0),
                "content": point.payload.get("content", ""),
                "title": point.payload.get("title", ""),
                "score": point.score,
                "search_type": "vector",
                "metadata": point.payload.get("metadata", {}),
                "doc_type": point.payload.get("doc_type", ""),
                "source": point.payload.get("source", ""),
            }
            for point in search_result
        ]

        logger.debug(f"Vector search returned {len(results)} results for hybrid search")
        return results
    except Exception as e:
        logger.error(f"Error in vector search for hybrid: {e}")
        raise
