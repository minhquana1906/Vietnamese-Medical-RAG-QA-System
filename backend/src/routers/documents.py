"""Document Management and Indexing Endpoints"""

import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from ..core.cache import invalidate_search_cache
from ..database import SessionLocal
from ..models import Chunk, Document, init_db, insert_document
from ..schemas.schema import (
    DocumentCreate,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    IndexingJobStatusResponse,
    IngestDatasetRequest,
    IngestDatasetResponse,
    ReindexDocumentResponse,
)
from ..tasks import chunk_and_index_document

router = APIRouter(prefix="/v1", tags=["Documents & Indexing"])

# Metrics (imported from main.py)
from ..core.metrics import document_indexing_duration_seconds, document_indexing_total


@router.post("/indexing/ingest-dataset", response_model=IngestDatasetResponse)
async def ingest_dataset(request: IngestDatasetRequest):
    """
    Ingest a HuggingFace dataset by loading, chunking, and indexing to Qdrant + Elasticsearch.

    Returns a job ID for tracking progress via GET /indexing/jobs/{job_id}.
    """
    try:
        start_time = time.time()

        logger.info(
            f"Starting dataset ingestion: {request.dataset_name} "
            f"(split={request.split}, limit={request.max_documents})"
        )

        # Load dataset from HuggingFace
        from datasets import load_dataset

        dataset = load_dataset(request.dataset_name, split=request.split)

        if request.max_documents:
            dataset = dataset.select(range(min(request.max_documents, len(dataset))))

        logger.info(f"Loaded {len(dataset)} documents from {request.dataset_name}")

        # Insert documents to database
        job_id = str(UUID(int=int(time.time() * 1000000) % (2**128)))
        documents_data = []

        try:
            for idx, item in enumerate(dataset):
                doc = insert_document(
                    title=item.get("title", f"Document {idx}"),
                    content=item.get("content", ""),
                    metadata={
                        "source": request.dataset_name,
                        "split": request.split,
                        "index": idx,
                        **item,
                    },
                )
                documents_data.append(
                    {
                        "id": str(doc.id),
                        "title": doc.title,
                        "content": doc.content,
                        "metadata": doc.metadata_,
                    }
                )

            logger.info(f"✅ Inserted {len(documents_data)} documents to database")

        except Exception as e:
            logger.error(f"Failed to insert documents: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        # Submit async indexing jobs
        for doc_data in documents_data:
            chunk_and_index_document.delay(
                doc_id=doc_data["id"],
                title=doc_data["title"],
                content=doc_data["content"],
                metadata=doc_data["metadata"],
            )

        duration = time.time() - start_time
        document_indexing_total.labels(status="submitted").inc(len(documents_data))

        return IngestDatasetResponse(
            job_id=job_id,
            dataset_name=request.dataset_name,
            total_documents=len(documents_data),
            status="submitted",
            message=f"Dataset ingestion started. {len(documents_data)} documents queued for indexing.",
        )

    except Exception as e:
        logger.error(f"Dataset ingestion failed: {e}")
        document_indexing_total.labels(status="failed").inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indexing/jobs/{job_id}", response_model=IndexingJobStatusResponse)
async def get_indexing_job_status(job_id: str):
    """
    Check the status of a background indexing job.

    Returns job status (pending, running, completed, failed) with progress information.
    """
    try:
        # Query database for job progress
        db = SessionLocal()
        try:
            # Count indexed vs total documents
            total_docs = db.query(Document).count()
            indexed_docs = db.query(Document).join(Chunk).distinct().count()

            progress = (indexed_docs / total_docs * 100) if total_docs > 0 else 0

            return IndexingJobStatusResponse(
                job_id=job_id,
                status="completed" if progress >= 100 else "running",
                progress={
                    "percent": progress,
                    "total_documents": total_docs,
                    "indexed_documents": indexed_docs,
                    "failed_documents": 0,
                    "message": f"Indexing progress: {indexed_docs}/{total_docs} documents",
                },
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/list", response_model=DocumentListResponse)
async def list_documents(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    is_indexed: Optional[bool] = Query(None),
):
    """
    List all documents with pagination and filtering.
    """
    try:
        db = SessionLocal()
        try:
            query = db.query(Document)

            # Apply filters
            if source:
                query = query.filter(Document.metadata_["source"].astext == source)
            # if doc_type:
            #     query = query.filter(Document.metadata_["type"].astext == doc_type)
            # if is_indexed is not None:
            #     query = query.filter(Document.is_indexed == is_indexed)

            # Get total count
            total = query.count()

            # Paginate
            documents = query.offset(offset).limit(limit).all()

            return DocumentListResponse(
                documents=[
                    DocumentResponse(
                        id=doc.id,
                        title=doc.title,
                        content=(
                            doc.content[:200] + "..."
                            if len(doc.content) > 200
                            else doc.content
                        ),
                        metadata=doc.metadata_,
                        is_indexed=False,
                        created_at=doc.createdAt.isoformat() if doc.createdAt else "",
                        updated_at=None,
                    )
                    for doc in documents
                ],
                total=total,
                limit=limit,
                offset=offset,
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/create", response_model=DocumentResponse, status_code=201)
async def create_document(request: DocumentCreate):
    """
    Manually create a document (not from HuggingFace dataset).

    Use POST /v1/indexing/reindex-document/{document_id} to chunk and index this document.
    """
    try:
        doc = insert_document(
            title=request.title,
            content=request.content,
            metadata=request.metadata or {},
        )

        logger.info(f"✅ Created document: {doc.id} - {doc.title}")

        return DocumentResponse(
            id=doc.id,
            title=doc.title,
            content=doc.content,
            metadata=doc.metadata_,
            is_indexed=False,
            created_at=doc.createdAt.isoformat() if doc.createdAt else "",
            updated_at=None,
        )

    except Exception as e:
        logger.error(f"Failed to create document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(document_id: UUID):
    """
    Get document details with all chunks.
    """
    try:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Get all chunks
            chunks = db.query(Chunk).filter(Chunk.documentId == document_id).all()

            return DocumentDetailResponse(
                id=doc.id,
                title=doc.title,
                content=doc.content,
                metadata=doc.metadata_,
                is_indexed=False,
                created_at=doc.createdAt.isoformat() if doc.createdAt else "",
                updated_at=None,
                chunks=[
                    {
                        "id": str(chunk.id),
                        "content": chunk.content,
                        "chunk_index": chunk.chunkIndex,
                        "metadata": chunk.metadata_,
                    }
                    for chunk in chunks
                ],
            )

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: UUID):
    """
    Delete document and all its chunks from PostgreSQL, Qdrant, and Elasticsearch.
    Invalidates search cache after deletion.
    """
    try:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Delete from Qdrant
            from ..core.vectorize import delete_points_by_document_id

            try:
                delete_points_by_document_id(str(document_id))
                logger.info(f"Deleted document {document_id} from Qdrant")
            except Exception as e:
                logger.warning(f"Failed to delete from Qdrant: {e}")

            # Delete from Elasticsearch
            from ..services.elasticsearch import ElasticsearchClient

            try:
                es_client = ElasticsearchClient()
                es_client.delete_document_chunks(str(document_id))
                logger.info(f"Deleted document {document_id} from Elasticsearch")
            except Exception as e:
                logger.warning(f"Failed to delete from Elasticsearch: {e}")

            # Delete chunks from database
            db.query(Chunk).filter(Chunk.documentId == document_id).delete()

            # Delete document from database
            db.delete(doc)
            db.commit()

            # Invalidate search cache
            invalidate_search_cache()

            logger.info(f"✅ Deleted document: {document_id}")

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/indexing/reindex-document/{document_id}",
    response_model=ReindexDocumentResponse,
)
async def reindex_document(document_id: UUID):
    """
    Reindex a specific document by deleting existing chunks and re-chunking/re-indexing.

    Returns a job ID for tracking progress via GET /indexing/jobs/{job_id}.
    """
    try:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Submit async reindexing job
            job_id = chunk_and_index_document.delay(str(document_id))

            logger.info(f"Submitted reindexing job for document: {document_id}")

            return ReindexDocumentResponse(
                job_id=str(job_id),
                document_id=document_id,
                status="submitted",
                message=f"Document reindexing started for {doc.title}",
            )

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reindex document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
