import uuid

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .configs.celery_config import get_celery_app
from .configs.setup import get_backend_settings
from .core.vectorize import search_vectors, upsert_points
from .services.brain import (
    detect_route,
    enhance_query_quality,
    get_tavily_agent_answer,
    qwen3_chat_complete,
)
from .services.chunking import fixed_semantic_chunking
from .services.embedding import get_embedding_service
from .services.rerank import get_qwen3_reranker
from .core.guardrails import get_guardrails_service

settings = get_backend_settings()

celery_app = get_celery_app(__name__)
celery_app.autodiscover_tasks()


@shared_task
def chunk_and_index_document(doc_id, title, content, metadata=None):
    """
    Chunk document and index to both Qdrant (vector) and Elasticsearch (keyword).

    This implements dual indexing strategy (T088) for hybrid search:
    1. Chunk document using fixed semantic strategy
    2. Generate embeddings for each chunk
    3. Store chunks in PostgreSQL with enhanced metadata (T095)
    4. Index to Qdrant (vector search) with metadata (T097)
    5. Index to Elasticsearch (keyword search) with metadata (T098)

    Args:
        doc_id: Document ID
        title: Document title
        content: Document content
        metadata: Document metadata dict with keys:
            - source: Dataset source
            - doc_type: Document type (clinical_guideline, drug_info, medical_qa, etc.)
            - language: Language code (default: vi)
            - section_title: Section title (optional)
            - page_number: Page number (optional)
            - any other custom fields
    """
    try:
        from uuid import UUID
        from .database import SessionLocal
        from .models import Chunk

        metadata = metadata or {}

        # Chunk the document using fixed semantic strategy (T087)
        nodes = fixed_semantic_chunking(
            text=content, metadata={"doc_id": doc_id, "title": title}
        )
        logger.info(
            f"Document chunked into {len(nodes)} chunks using fixed semantic strategy"
        )

        # Get services
        embedding_service = get_embedding_service()
        from .services.elasticsearch import get_elasticsearch_client

        es_client = get_elasticsearch_client()

        # Generate embeddings and prepare points for dual indexing
        qdrant_points = []
        elasticsearch_docs = []
        db_chunks = []  # Store chunks in database (T095)

        # Extract metadata fields (T095)
        doc_source = metadata.get("source", "")
        doc_type = metadata.get("doc_type", "medical_qa")
        language = metadata.get("language", "vi")
        section_title = metadata.get("section_title")
        page_number = metadata.get("page_number")

        # OPTIMIZATION: Generate embeddings in batch for better performance
        logger.info(f"Generating embeddings for {len(nodes)} chunks in batch...")
        chunk_texts = [node.text for node in nodes]
        batch_embeddings = embedding_service.embed_batch_documents(
            documents=chunk_texts,
            batch_size=512,  # Large batch size for dataset ingestion
        )
        logger.info(f"✅ Generated {len(batch_embeddings)} embeddings in batch")

        for chunk_index, (node, embedding) in enumerate(zip(nodes, batch_embeddings)):
            if not embedding:
                logger.warning(
                    f"Failed to generate embedding for chunk {chunk_index}: {node.text[:50]}..."
                )
                continue

            # Generate unique chunk ID
            chunk_id = str(uuid.uuid4())

            # Calculate token count for metadata
            token_count = len(node.text.split())  # Rough estimate

            # Prepare enhanced metadata (T095: source_document_id, chunk_index, section_title, page_number)
            chunk_metadata = {
                "source_document_id": doc_id,
                "chunk_index": chunk_index,
                "title": title,
                "doc_type": doc_type,
                "source": doc_source,
                "language": language,
                "token_count": token_count,
            }

            # Add optional fields if present
            if section_title:
                chunk_metadata["section_title"] = section_title
            if page_number is not None:
                chunk_metadata["page_number"] = page_number

            # Add any additional metadata from document
            for key, value in metadata.items():
                if key not in [
                    "source",
                    "doc_type",
                    "language",
                    "section_title",
                    "page_number",
                ]:
                    chunk_metadata[key] = value

            # Prepare Qdrant point with enhanced metadata (T097)
            qdrant_point = {
                "id": chunk_id,
                "embedding": embedding,
                "metadata": {
                    "content": node.text,
                    **chunk_metadata,  # Include all enhanced metadata
                },
            }
            qdrant_points.append(qdrant_point)

            # Prepare Elasticsearch document with enhanced metadata (T098)
            elasticsearch_docs.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "chunk_index": chunk_index,
                    "content": node.text,
                    "title": title,
                    "doc_type": doc_type,
                    "source": doc_source,
                    "language": language,
                    "metadata": chunk_metadata,
                }
            )

            # Prepare database chunk (T095)
            db_chunks.append(
                {
                    "id": UUID(chunk_id),
                    "documentId": UUID(doc_id),
                    "chunkIndex": chunk_index,
                    "content": node.text,
                    "metadata_": chunk_metadata,
                }
            )

        # Store chunks in database (T095)
        if db_chunks:
            with SessionLocal() as db:
                for chunk_data in db_chunks:
                    chunk = Chunk(**chunk_data)
                    db.add(chunk)
                db.commit()
            logger.info(f"✅ Stored {len(db_chunks)} chunks in PostgreSQL")

        # Index to Qdrant (vector database) with enhanced metadata (T097)
        if qdrant_points:
            upsert_points(
                qdrant_points, collection_name=settings.default_collection_name
            )
            logger.info(
                f"✅ Indexed {len(qdrant_points)} chunks to Qdrant with enhanced metadata"
            )
        else:
            logger.warning(f"⚠️ No embeddings generated for document '{title}'")

        # Index to Elasticsearch (keyword search) with enhanced metadata (T098)
        if elasticsearch_docs:
            indexed_count = 0
            for es_doc in elasticsearch_docs:
                success = es_client.index_chunk(
                    chunk_id=es_doc["chunk_id"],
                    document_id=es_doc["document_id"],
                    chunk_index=es_doc["chunk_index"],
                    content=es_doc["content"],
                    title=es_doc["title"],
                    doc_type=es_doc["doc_type"],
                    source=es_doc["source"],
                    language=es_doc["language"],
                    metadata=es_doc["metadata"],
                )
                if success:
                    indexed_count += 1

            logger.info(
                f"✅ Indexed {indexed_count}/{len(elasticsearch_docs)} chunks to Elasticsearch with enhanced metadata"
            )

        logger.info(
            f"🎉 Dual indexing complete for document '{title}': "
            f"{len(qdrant_points)} chunks → Qdrant (vector) + Elasticsearch (keyword)"
        )

        return {"chunks_created": len(qdrant_points)}

    except Exception as e:
        logger.error(f"❌ Error in chunking and indexing document: {e}")
        raise


@shared_task()
def bot_route_answer_message(history, question):
    # detect the route
    route = detect_route(history, question)
    logger.info(f"Bot route: {route}")
    if route == "medical":
        return rag_qa_task(history, question)
    elif route == "general":
        response = qwen3_chat_complete(
            messages=history + [{"role": "user", "content": question}],
            temperature=0.7,
            max_tokens=1024,
            use_fallback=True,  # Enable fallback to prevent None return
        )
        # Fallback to safe message if still None
        if response is None:
            return "Xin lỗi, hệ thống đang quá tải. Vui lòng thử lại sau."
        return response


@shared_task(
    bind=True,
    time_limit=300,  # 5 minutes hard timeout
    soft_time_limit=180,  # 3 minutes soft timeout
    max_retries=0,  # No automatic retries
)
def rag_qa_task(self, history, question):
    """
    RAG QA task with Qwen3Guard input/output validation.

    Flow:
    1. Validate user input with Qwen3Guard
    2. If valid, proceed with RAG pipeline
    3. Generate response with Qwen3
    4. Validate response with Qwen3Guard
    5. If invalid, regenerate with feedback (max 2 retries)
    6. Return final validated response

    Args:
        self: Celery task instance (for cancellation check)
        history: Conversation history
        question: User question
    """
    try:
        # ============================================
        # STEP 1: INPUT VALIDATION (Qwen3Guard)
        # ============================================
        logger.info("=" * 60)
        logger.info("🛡️  STEP 1: Input Validation with Qwen3Guard")
        logger.info("=" * 60)

        guardrails = get_guardrails_service()
        is_valid_input, violation_category, input_metadata = guardrails.validate_query(
            question
        )

        if not is_valid_input:
            rejection_message = guardrails.get_rejection_message(
                violation_category, language="vi"
            )
            logger.warning(
                f"❌ User query REJECTED by guardrails: category={violation_category}, "
                f"metadata={input_metadata}"
            )
            logger.info(f"📤 Returning rejection message: {rejection_message}")
            return rejection_message

        logger.info(
            f"✅ User query PASSED input validation (confidence={input_metadata.get('confidence', 'N/A')})"
        )

        # ============================================
        # STEP 2: RAG PIPELINE (Query Enhancement + Retrieval + Reranking)
        # ============================================
        logger.info("=" * 60)
        logger.info("🔍 STEP 2: RAG Pipeline Processing")
        logger.info("=" * 60)

        new_question = enhance_query_quality(history, question)
        logger.info(f"📝 Enhanced query: {new_question[:100]}...")

        # Get embedding service (Qwen3)
        embedding_service = get_embedding_service()

        # Generate embedding for question using Qwen3 (WITH instruction prefix)
        logger.info(
            "🔢 Generating embedding with Qwen3-Embedding (instruction-aware)..."
        )
        question_embedding = embedding_service.embed_query(new_question, use_cache=True)

        if not question_embedding:
            logger.error("❌ Failed to generate embedding for question")
            return "Xin lỗi, không thể xử lý câu hỏi của bạn lúc này."

        # Retrieve top-k most relevant documents using HYBRID SEARCH (vector + keyword)
        logger.info(
            f"🔎 Performing hybrid search (vector + keyword, top_k={settings.top_k})..."
        )

        from .core.hybrid_search import hybrid_search
        from .services.elasticsearch import get_elasticsearch_client
        from .core.vectorize import search_vectors_for_hybrid

        # Define search functions
        def vector_search_fn(query, top_k, doc_type_filter=None, source_filter=None):
            return search_vectors_for_hybrid(
                query_vector=question_embedding,
                top_k=top_k,
                collection_name=settings.default_collection_name,
                doc_type_filter=doc_type_filter,
                source_filter=source_filter,
            )

        def keyword_search_fn(query, top_k, doc_type_filter=None, source_filter=None):
            es_client = get_elasticsearch_client()
            return es_client.search_bm25(
                query=query,
                top_k=top_k,
                doc_type_filter=doc_type_filter,
                source_filter=source_filter,
            )

        # Perform hybrid search (RRF fusion)
        relevant_docs = hybrid_search(
            query=new_question,
            vector_search_fn=vector_search_fn,
            keyword_search_fn=keyword_search_fn,
            top_k=settings.top_k,
            rrf_k=60,  # RRF parameter
            use_cache=True,
        )
        logger.info(
            f"📚 Hybrid search retrieved {len(relevant_docs)} documents (RRF fusion)"
        )

        # Rerank using Qwen3 Reranker
        logger.info("⚡ Reranking with Qwen3-Reranker...")
        reranker = get_qwen3_reranker()
        if relevant_docs:
            reranked_results, rerank_context = reranker.rerank(
                new_question, relevant_docs, top_n=5
            )
            if reranked_results:
                logger.info(
                    f"📊 Reranking complete: top score={reranked_results[0]['relevance_score']:.3f}"
                )
        else:
            reranked_results, rerank_context = None, None
            logger.warning("⚠️  No documents retrieved from vector DB")

        # Check if RAG results have sufficient confidence. If best score is too low, use web search
        use_web_search = False
        if not reranked_results or (
            reranked_results and reranked_results[0]["relevance_score"] < 0.5
        ):
            logger.info(
                f"⚠️  RAG confidence low (best score: {reranked_results[0]['relevance_score'] if reranked_results else 0:.3f}), "
                f"will use web search as fallback"
            )
            use_web_search = True

        formatted_context = (
            rerank_context
            if reranked_results
            else "Can't find relevant documents from knowledge base."
        )

        # ============================================
        # STEP 3: RESPONSE GENERATION (Qwen3 + Validation Loop)
        # ============================================
        logger.info("=" * 60)
        logger.info("🤖 STEP 3: Response Generation with Output Validation")
        logger.info("=" * 60)

        # Build the message chain with intelligent history management
        from .services.summarizer import summarize_old_messages

        messages = [{"role": "system", "content": settings.system_prompt}]

        history_with_system = messages + history
        optimized_history = summarize_old_messages(
            history_with_system, target_tokens=2000
        )
        messages = optimized_history

        max_retries = 0  # DISABLED: No retry for output validation (testing mode)
        retry_count = 0
        final_response = None

        while retry_count <= max_retries:
            # Check if task was revoked (cancelled by user)
            if self.request.id and self.AsyncResult(self.request.id).state == "REVOKED":
                logger.warning("❌ Task was cancelled by user, aborting...")
                return "Yêu cầu đã bị hủy bởi người dùng."

            logger.info(f"🔄 Generation attempt {retry_count + 1}/{max_retries + 1}")

            if use_web_search:
                # Use web search with Tavily agent
                user_message = {
                    "role": "user",
                    "content": f"RAG Context (can be insufficient):\n{formatted_context}\n\nQuestion: {new_question}\n\nNote: Information in RAG context may be insufficient. Please search for additional information from the internet and ALWAYS provide the source with the full URL.",
                }

                # Add retry feedback if this is a retry
                if retry_count > 0 and "feedback" in locals():
                    user_message[
                        "content"
                    ] += f"\n\n⚠️ IMPORTANT FEEDBACK FROM SAFETY CHECK:\n{feedback}\n\nPlease revise your response accordingly."

                messages_with_query = messages + [user_message]
                response = get_tavily_agent_answer(messages_with_query)
                logger.info("🌐 Response generated with web search fallback")
            else:
                # Use standard RAG response with Qwen3
                user_message = {
                    "role": "user",
                    "content": settings.rag_prompt.format(
                        context=formatted_context, question=new_question
                    ),
                }

                # Add retry feedback if this is a retry
                if retry_count > 0 and "feedback" in locals():
                    user_message[
                        "content"
                    ] += f"\n\n⚠️ IMPORTANT FEEDBACK FROM SAFETY CHECK:\n{feedback}\n\nPlease revise your response accordingly."

                messages_with_query = messages + [user_message]

                # Use Qwen3 generation model with reasonable max_tokens
                # Medical responses typically 500-800 tokens, 1024 is sufficient
                response = qwen3_chat_complete(
                    messages=messages_with_query,
                    temperature=0.7,
                    max_tokens=1024,  # Reduced from 2048 to prevent timeouts
                    use_fallback=True,
                )

                if not response:
                    logger.error("❌ Failed to generate response with Qwen3")
                    return "Xin lỗi, không thể tạo câu trả lời lúc này."

                logger.info(
                    f"✅ RAG response generated successfully with Qwen3 ({len(response)} chars)"
                )

            # ============================================
            # STEP 4: OUTPUT VALIDATION (Qwen3Guard)
            # ============================================
            logger.info("-" * 60)
            logger.info(f"🛡️  STEP 4: Output Validation (Attempt {retry_count + 1})")
            logger.info("-" * 60)

            is_valid_output, output_violation, output_metadata = (
                guardrails.validate_response(
                    response, question, max_retries=max_retries
                )
            )

            if is_valid_output:
                logger.info(
                    f"✅ Response PASSED output validation (confidence={output_metadata.get('confidence', 'N/A')})"
                )
                final_response = response
                break  # Success! Exit retry loop
            else:
                logger.warning(
                    f"❌ Response FAILED output validation: category={output_violation}, "
                    f"attempt={retry_count + 1}/{max_retries + 1}"
                )

                if retry_count < max_retries:
                    # Get feedback for regeneration
                    feedback = output_metadata.get(
                        "feedback",
                        "Please revise your response to be safer and more appropriate.",
                    )
                    logger.info(f"📝 Regeneration feedback: {feedback}")
                    logger.info(f"🔄 Retrying generation with feedback...")
                    retry_count += 1
                else:
                    # Max retries exceeded - return safe fallback
                    logger.error(
                        f"❌ Max retries ({max_retries}) exceeded. Returning safe fallback response."
                    )
                    final_response = (
                        "Xin lỗi, tôi không thể tạo ra câu trả lời phù hợp cho câu hỏi này. "
                        "Vui lòng thử lại với cách diễn đạt khác hoặc liên hệ với bác sĩ để được tư vấn trực tiếp."
                    )
                    break

        # ============================================
        # STEP 5: RETURN FINAL RESPONSE
        # ============================================
        logger.info("=" * 60)
        logger.info("📤 STEP 5: Returning Final Response")
        logger.info("=" * 60)
        logger.info(f"✅ Final response: {final_response[:150]}...")
        logger.info(f"📊 Total generation attempts: {retry_count + 1}")

        return final_response

    except SoftTimeLimitExceeded:
        logger.error("❌ Task exceeded soft time limit (240s), aborting...")
        return "Xin lỗi, yêu cầu của bạn đã vượt quá thời gian xử lý cho phép. Vui lòng thử lại với câu hỏi ngắn gọn hơn."

    except Exception as e:
        logger.error(f"❌ Error in RAG QA task: {e}", exc_info=True)
        return "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."


@shared_task(bind=True)
def ingest_dataset_task(
    self,
    dataset_name: str,
    dataset_config: str = None,
    split: str = "train",
    doc_type: str = None,
    max_documents: int = None,
    batch_size: int = 10,  # NEW: Process documents in batches
):
    """
    Load a HuggingFace dataset and index all documents to Qdrant + Elasticsearch.

    OPTIMIZATIONS:
    - Batch database commits (reduce DB overhead)
    - Batch embedding generation (already in chunk_and_index_document)
    - Batch Elasticsearch indexing (via bulk API)

    Args:
        dataset_name: HuggingFace dataset identifier
        dataset_config: Dataset configuration name (optional)
        split: Dataset split to load (default: "train")
        doc_type: Document type for all documents
        max_documents: Limit number of documents (for testing)
        batch_size: Number of documents to process in each batch (default: 10)

    Returns:
        dict: {
            "documents_indexed": int,
            "chunks_indexed": int,
            "duration_seconds": float,
        }
    """
    import time
    import hashlib
    from datasets import load_dataset
    from .database import SessionLocal
    from .models import Document, Chunk

    start_time = time.time()
    documents_indexed = 0
    chunks_indexed = 0

    try:
        logger.info(
            f"Starting dataset ingestion: {dataset_name} (split={split}, batch_size={batch_size})"
        )

        # Update state to running
        self.update_state(
            state="PROGRESS",
            meta={
                "documents_processed": 0,
                "total_documents": 0,
                "chunks_created": 0,
            },
        )

        # Load dataset from HuggingFace
        logger.info(f"Loading dataset from HuggingFace Hub: {dataset_name}")
        dataset = load_dataset(dataset_name, dataset_config, split=split)

        total_docs = (
            len(dataset) if max_documents is None else min(len(dataset), max_documents)
        )
        logger.info(f"Dataset loaded: {total_docs} documents to process")

        # OPTIMIZATION 1: Process documents in batches
        document_batch = []

        with SessionLocal() as db:
            for idx, item in enumerate(dataset):
                # CRITICAL FIX: Check max_documents against PROCESSED count, not dataset index
                if max_documents and documents_indexed >= max_documents:
                    logger.info(
                        f"✅ Reached max_documents limit ({max_documents}), stopping ingestion"
                    )
                    break

                # Extract document fields (adapt to dataset structure)
                # Common field names: title, text, content, question, answer, etc.
                title = item.get("title") or item.get("question") or f"Document {idx}"
                content = (
                    item.get("text") or item.get("content") or item.get("answer") or ""
                )

                if not content:
                    logger.warning(f"Skipping document {idx}: no content found")
                    continue

                # Calculate content hash for incremental updates (T102a)
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                # Check if document already exists with same hash
                existing_doc = (
                    db.query(Document)
                    .filter(Document.metadata_["content_hash"].astext == content_hash)
                    .first()
                )

                if existing_doc:
                    logger.info(
                        f"Document {idx} already indexed (hash match), skipping"
                    )
                    continue

                # Create document metadata with version tracking (T102b)
                metadata = {
                    "source": dataset_name,
                    "doc_type": doc_type or "medical_qa",
                    "language": "vi",
                    "dataset_split": split,
                    "content_hash": content_hash,
                    "is_indexed": False,
                    "dataset_version": "1.0",  # T102b: Track dataset version for incremental updates
                    "indexed_at": None,  # Will be set when indexing completes
                }

                # Add any additional fields from dataset
                for key, value in item.items():
                    if key not in ["title", "text", "content", "question", "answer"]:
                        metadata[key] = value

                # Add to batch
                document_batch.append(
                    {
                        "title": title,
                        "content": content,
                        "metadata": metadata,
                        "idx": idx,
                    }
                )

                # OPTIMIZATION 2: Process batch when full or at end
                if len(document_batch) >= batch_size or idx == len(dataset) - 1:
                    logger.info(
                        f"Processing batch of {len(document_batch)} documents..."
                    )

                    # Create documents in database (batch commit)
                    new_docs = []
                    for doc_data in document_batch:
                        new_doc = Document(
                            title=doc_data["title"],
                            content=doc_data["content"],
                            metadata_=doc_data["metadata"],
                        )
                        db.add(new_doc)
                        new_docs.append((new_doc, doc_data))

                    # OPTIMIZATION 3: Single commit for batch
                    db.commit()

                    # Refresh all documents to get IDs
                    for new_doc, _ in new_docs:
                        db.refresh(new_doc)

                    logger.info(f"✅ Committed {len(new_docs)} documents to database")

                    # Chunk and index each document (embedding is already batched inside)
                    for new_doc, doc_data in new_docs:
                        logger.info(
                            f"Chunking and indexing document {doc_data['idx']+1}/{total_docs}: {doc_data['title'][:50]}"
                        )
                        chunk_result = chunk_and_index_document(
                            str(new_doc.id),
                            doc_data["title"],
                            doc_data["content"],
                            metadata=doc_data["metadata"],
                        )

                        # Update document as indexed with timestamp (T102b)
                        from datetime import datetime

                        new_doc.metadata_["is_indexed"] = True
                        new_doc.metadata_["indexed_at"] = datetime.utcnow().isoformat()

                        documents_indexed += 1
                        chunks_indexed += chunk_result.get("chunks_created", 0)

                    # OPTIMIZATION 4: Batch commit for status updates
                    db.commit()

                    # Update progress
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "documents_processed": documents_indexed,
                            "total_documents": total_docs,
                            "chunks_created": chunks_indexed,
                        },
                    )

                    logger.info(
                        f"Progress: {documents_indexed}/{total_docs} documents, "
                        f"{chunks_indexed} chunks created"
                    )

                    # Clear batch
                    document_batch = []

        duration = time.time() - start_time

        logger.info(
            f"✅ Dataset ingestion completed: {documents_indexed} documents, "
            f"{chunks_indexed} chunks in {duration:.2f}s"
        )

        return {
            "documents_indexed": documents_indexed,
            "chunks_indexed": chunks_indexed,
            "duration_seconds": duration,
        }

    except Exception as e:
        logger.error(f"❌ Dataset ingestion failed: {e}", exc_info=True)
        raise


@shared_task(bind=True)
def reindex_document_task(self, document_id: str):
    """
    Reindex a specific document by deleting existing chunks and re-chunking/re-indexing.

    Implements T092: Reindex endpoint.

    Args:
        document_id: Document ID (UUID string)

    Returns:
        dict: {
            "document_id": str,
            "chunks_created": int,
            "duration_seconds": float,
        }
    """
    import time
    from uuid import UUID
    from .database import SessionLocal
    from .models import Document, Chunk
    from .core.vectorize import qdrant_client, settings as vectorize_settings
    from .services.elasticsearch import es_client, settings as es_settings

    start_time = time.time()

    try:
        doc_uuid = UUID(document_id)

        logger.info(f"Starting document reindexing: {document_id}")

        with SessionLocal() as db:
            # Get document
            doc = db.query(Document).filter(Document.id == doc_uuid).first()

            if not doc:
                raise ValueError(f"Document not found: {document_id}")

            # Get existing chunks
            existing_chunks = db.query(Chunk).filter(Chunk.documentId == doc_uuid).all()
            chunk_ids = [str(chunk.id) for chunk in existing_chunks]

            logger.info(f"Found {len(chunk_ids)} existing chunks to delete")

            # Delete from Qdrant
            if chunk_ids:
                try:
                    qdrant_client.delete(
                        collection_name=vectorize_settings.qdrant_collection_name,
                        points_selector=chunk_ids,
                    )
                    logger.info(f"Deleted {len(chunk_ids)} chunks from Qdrant")
                except Exception as e:
                    logger.warning(f"Failed to delete from Qdrant: {e}")

            # Delete from Elasticsearch
            if chunk_ids:
                try:
                    for chunk_id in chunk_ids:
                        try:
                            es_client.delete(
                                index=es_settings.elasticsearch_index,
                                id=chunk_id,
                                ignore=[404],
                            )
                        except Exception as e:
                            logger.warning(f"Failed to delete chunk {chunk_id}: {e}")
                    logger.info(f"Deleted {len(chunk_ids)} chunks from Elasticsearch")
                except Exception as e:
                    logger.warning(f"Failed to delete from Elasticsearch: {e}")

            # Delete chunks from database
            for chunk in existing_chunks:
                db.delete(chunk)
            db.commit()

            logger.info("Deleted existing chunks from database")

            # Re-chunk and re-index with document metadata
            doc_metadata = doc.metadata_ or {}
            chunk_result = chunk_and_index_document(
                str(doc.id),
                doc.title,
                doc.content,
                metadata=doc_metadata,  # Pass document metadata
            )

            # Update document as indexed
            if doc.metadata_ is None:
                doc.metadata_ = {}
            doc.metadata_["is_indexed"] = True
            db.commit()

        duration = time.time() - start_time

        logger.info(
            f"✅ Document reindexing completed: {document_id}, "
            f"{chunk_result.get('chunks_created', 0)} chunks in {duration:.2f}s"
        )

        return {
            "document_id": document_id,
            "chunks_created": chunk_result.get("chunks_created", 0),
            "duration_seconds": duration,
        }

    except Exception as e:
        logger.error(f"❌ Document reindexing failed: {e}", exc_info=True)
        raise
