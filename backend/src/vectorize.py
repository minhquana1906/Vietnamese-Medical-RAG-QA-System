from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

from .config import get_backend_settings

settings = get_backend_settings()


def get_qdrant_client(host="localhost", port=6333):
    try:
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


def batch_upsert(points, batch_size=settings.batch_points):
    logger.info(f"⬆️ Uploading {len(points)} points (batch size: {batch_size})...")

    total_batches = (len(points) + batch_size - 1) // batch_size

    for i in tqdm(
        range(0, len(points), batch_size), total=total_batches, desc="Uploading"
    ):
        batch = points[i : i + batch_size]
        try:
            upsert_points(batch, collection_name=settings.default_collection_name)
        except Exception as e:
            logger.error(f"Batch {i//batch_size + 1} failed: {e}")
            raise

    logger.info("All batches uploaded successfully")


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
