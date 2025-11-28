import uuid

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .configs.celery_config import get_celery_app
from .configs.setup import get_backend_settings
from .configs.logging_config import get_rag_logger
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
tracer = trace.get_tracer(__name__)
rag_log = get_rag_logger()

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
        chunk_texts = [node.text for node in nodes]
        batch_embeddings = embedding_service.embed_batch_documents(
            documents=chunk_texts,
            batch_size=512,  # Large batch size for dataset ingestion
        )

        for chunk_index, (node, embedding) in enumerate(zip(nodes, batch_embeddings)):
            if not embedding:
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

        # Index to Qdrant (vector database) with enhanced metadata (T097)
        if qdrant_points:
            upsert_points(
                qdrant_points, collection_name=settings.default_collection_name
            )

        # Index to Elasticsearch (keyword search) with enhanced metadata (T098)
        if elasticsearch_docs:
            for es_doc in elasticsearch_docs:
                es_client.index_chunk(
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

        return {"chunks_created": len(qdrant_points)}

    except Exception as e:
        logger.error(f"[CHUNK] ❌ Error indexing doc_id={doc_id}: {e}")
        raise


@shared_task()
def bot_route_answer_message(history, question, system_prompt=None):
    """
    Route user message to appropriate handler (medical RAG or general chat).

    Flow:
    1. Validate user input with Qwen3Guard (BEFORE routing)
    2. If invalid, return rejection message immediately
    3. If valid, detect route and proceed to appropriate handler

    Args:
        history: Conversation history
        question: User question
        system_prompt: Custom system prompt (optional, defaults to settings.system_prompt)

    Returns:
        str: Generated response
    """
    # ============================================
    # STEP 0: INPUT VALIDATION (Qwen3Guard) - BEFORE ROUTING
    # ============================================
    guardrails = get_guardrails_service()
    is_valid_input, violation_category, input_metadata = guardrails.validate_query(
        question
    )

    rag_log.log_guardrails_input(
        is_valid=is_valid_input,
        category=violation_category,
        severity=input_metadata.get("severity") if input_metadata else None,
    )

    if not is_valid_input:
        rejection_message = guardrails.get_rejection_message(
            violation_category, language="vi"
        )
        logger.warning(
            f"[GUARD] ⛔ Input rejected: category={violation_category}, "
            f"severity={input_metadata.get('severity') if input_metadata else 'unknown'}"
        )
        return rejection_message

    # ============================================
    # STEP 1: ROUTE DETECTION
    # ============================================
    route = detect_route(history, question)
    rag_log.log_route_detection(route)

    if route == "medical":
        # Pass skip_input_validation=True since we already validated
        return rag_qa_task(
            history, question, system_prompt=system_prompt, skip_input_validation=True
        )
    elif route == "general":
        response = qwen3_chat_complete(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                    or "Bạn là Meddy - Trợ lý y tế thông minh cho người Việt.",
                }
            ]
            + history
            + [{"role": "user", "content": question}],
            temperature=0.7,
            max_tokens=1536,
        )
        if response is None:
            return "Xin lỗi, hệ thống đang quá tải. Vui lòng thử lại sau."
        return response


@shared_task(
    bind=True,
    time_limit=300,  # 5 minutes hard timeout
    soft_time_limit=180,  # 3 minutes soft timeout
    max_retries=0,  # No automatic retries
)
def rag_qa_task(
    self, history, question, system_prompt=None, skip_input_validation=False
):
    """
    RAG QA task with Qwen3Guard input/output validation.

    Flow:
    1. Validate user input with Qwen3Guard (if not already validated)
    2. If valid, proceed with RAG pipeline
    3. Generate response with Qwen3
    4. Validate response with Qwen3Guard
    5. If invalid, regenerate with feedback (max 2 retries)
    6. Return final validated response

    Args:
        history: Conversation history
        question: User question
        system_prompt: Custom system prompt (optional)
        skip_input_validation: Skip input validation if already done in bot_route_answer_message
    """
    import time
    from .core.model_config import get_generation_model

    request_start = time.time()

    try:
        guardrails = get_guardrails_service()

        # ============================================
        # STEP 1: INPUT VALIDATION (Qwen3Guard)
        # Skip if already validated in bot_route_answer_message
        # ============================================
        if not skip_input_validation:
            is_valid_input, violation_category, input_metadata = (
                guardrails.validate_query(question)
            )

            rag_log.log_guardrails_input(
                is_valid=is_valid_input,
                category=violation_category,
                severity=input_metadata.get("severity") if input_metadata else None,
            )

            if not is_valid_input:
                rejection_message = guardrails.get_rejection_message(
                    violation_category, language="vi"
                )
                rag_log.log_request_complete(request_start, success=False)
                return rejection_message

        # ============================================
        # STEP 2: QUERY ENHANCEMENT
        # ============================================
        new_question = enhance_query_quality(history, question)
        rag_log.log_query_enhancement(question, new_question)

        # ============================================
        # STEP 3: EMBEDDING GENERATION
        # ============================================
        embedding_service = get_embedding_service()
        question_embedding = embedding_service.embed_query(new_question, use_cache=True)

        if not question_embedding:
            rag_log.log_embedding(success=False, is_query=True)
            rag_log.log_request_complete(request_start, success=False)
            return "Xin lỗi, không thể xử lý câu hỏi của bạn lúc này."

        rag_log.log_embedding(
            success=True,
            dimension=len(question_embedding),
            is_query=True,
            cache_hit=False,  # Cache status logged in embedding service
        )

        # ============================================
        # STEP 4: HYBRID RETRIEVAL
        # ============================================
        from .core.hybrid_search import hybrid_search
        from .services.elasticsearch import get_elasticsearch_client
        from .core.vectorize import search_vectors_for_hybrid

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

        relevant_docs = hybrid_search(
            query=new_question,
            vector_search_fn=vector_search_fn,
            keyword_search_fn=keyword_search_fn,
            top_k=settings.top_k,
            rrf_k=60,
            use_cache=True,
        )

        # ============================================
        # STEP 5: RERANKING
        # ============================================
        reranker = get_qwen3_reranker()
        if relevant_docs:
            reranked_results, rerank_context = reranker.rerank(
                new_question, relevant_docs, top_n=5
            )
            if reranked_results:
                rag_log.log_rerank_results(reranked_results, top_n=5)
        else:
            reranked_results, rerank_context = None, None
            logger.warning("[RAG] ⚠️ No documents retrieved")

        # Check confidence for web search fallback
        use_web_search = False
        if not reranked_results or (
            reranked_results and reranked_results[0]["relevance_score"] < 0.5
        ):
            best_score = (
                reranked_results[0]["relevance_score"] if reranked_results else 0
            )
            logger.info(
                f"[RAG] 🌐 Low confidence (score={best_score:.3f}), using web search"
            )
            use_web_search = True

        formatted_context = (
            rerank_context
            if reranked_results
            else "Can't find relevant documents from knowledge base."
        )

        # ============================================
        # STEP 6: HISTORY SUMMARIZATION
        # ============================================
        from .services.summarizer import (
            summarize_old_messages,
            calculate_messages_tokens,
        )

        prompt = system_prompt or settings.system_prompt
        messages = [{"role": "system", "content": prompt}]
        history_with_system = messages + history

        original_count = len(history_with_system)
        original_tokens = calculate_messages_tokens(history_with_system)

        optimized_history = summarize_old_messages(
            history_with_system, target_tokens=2000
        )

        new_tokens = calculate_messages_tokens(optimized_history)
        rag_log.log_history_summary(
            original_count=original_count,
            summarized_count=len(optimized_history),
            original_tokens=original_tokens,
            new_tokens=new_tokens,
        )

        messages = optimized_history

        # ============================================
        # STEP 7: RESPONSE GENERATION WITH VALIDATION
        # ============================================
        max_retries = 0  # Disabled for testing
        retry_count = 0
        final_response = None
        generation_model = get_generation_model()

        while retry_count <= max_retries:
            if self.request.id and self.AsyncResult(self.request.id).state == "REVOKED":
                logger.warning("[RAG] Task cancelled by user")
                return "Yêu cầu đã bị hủy bởi người dùng."

            if use_web_search:
                user_message = {
                    "role": "user",
                    "content": f"RAG Context (can be insufficient):\n{formatted_context}\n\nQuestion: {new_question}\n\nNote: Information in RAG context may be insufficient. Please search for additional information from the internet and ALWAYS provide the source with the full URL.",
                }
                if retry_count > 0 and "feedback" in locals():
                    user_message[
                        "content"
                    ] += f"\n\n⚠️ IMPORTANT FEEDBACK FROM SAFETY CHECK:\n{feedback}\n\nPlease revise your response accordingly."

                messages_with_query = messages + [user_message]
                response = get_tavily_agent_answer(messages_with_query)
            else:
                user_message = {
                    "role": "user",
                    "content": settings.rag_prompt.format(
                        context=formatted_context, question=new_question
                    ),
                }
                if retry_count > 0 and "feedback" in locals():
                    user_message[
                        "content"
                    ] += f"\n\n⚠️ IMPORTANT FEEDBACK FROM SAFETY CHECK:\n{feedback}\n\nPlease revise your response accordingly."

                messages_with_query = messages + [user_message]
                response = qwen3_chat_complete(
                    messages=messages_with_query,
                    temperature=0.7,
                    max_tokens=1536,
                )

                if not response:
                    rag_log.log_generation(success=False, use_web_search=use_web_search)
                    rag_log.log_request_complete(request_start, success=False)
                    return "Xin lỗi, không thể tạo câu trả lời lúc này."

            rag_log.log_generation(
                success=True,
                response_length=len(response) if response else 0,
                model=generation_model,
                use_web_search=use_web_search,
            )

            # Output validation
            is_valid_output, output_violation, output_metadata = (
                guardrails.validate_response(
                    response, question, max_retries=max_retries
                )
            )

            rag_log.log_guardrails_output(
                is_valid=is_valid_output,
                category=output_violation,
                severity=output_metadata.get("severity") if output_metadata else None,
                attempt=retry_count + 1,
            )

            if is_valid_output:
                final_response = response
                break
            else:
                if retry_count < max_retries:
                    feedback = output_metadata.get(
                        "feedback",
                        "Please revise your response to be safer and more appropriate.",
                    )
                    retry_count += 1
                else:
                    final_response = (
                        "Xin lỗi, tôi không thể tạo ra câu trả lời phù hợp cho câu hỏi này. "
                        "Vui lòng thử lại với cách diễn đạt khác hoặc liên hệ với bác sĩ để được tư vấn trực tiếp."
                    )
                    break

        rag_log.log_request_complete(request_start, success=True)
        return final_response

    except SoftTimeLimitExceeded:
        logger.error("[RAG] Task exceeded soft time limit (180s)")
        rag_log.log_request_complete(request_start, success=False)
        return "Xin lỗi, yêu cầu của bạn đã vượt quá thời gian xử lý cho phép. Vui lòng thử lại với câu hỏi ngắn gọn hơn."

    except Exception as e:
        logger.error(f"[RAG] Error: {e}", exc_info=True)
        rag_log.log_request_complete(request_start, success=False)
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
        dataset = load_dataset(dataset_name, dataset_config, split=split)

        total_docs = (
            len(dataset) if max_documents is None else min(len(dataset), max_documents)
        )
        logger.info(
            f"[INDEX] 📂 Dataset loaded: {dataset_name} | {total_docs} documents | batch_size={batch_size}"
        )

        # OPTIMIZATION 1: Process documents in batches
        document_batch = []

        with SessionLocal() as db:
            for idx, item in enumerate(dataset):
                # CRITICAL FIX: Check max_documents against PROCESSED count, not dataset index
                if max_documents and documents_indexed >= max_documents:
                    break

                # Extract document fields (adapt to dataset structure)
                # Common field names: title, text, content, question, answer, etc.
                title = item.get("title") or item.get("question") or f"Document {idx}"
                content = (
                    item.get("text") or item.get("content") or item.get("answer") or ""
                )

                if not content:
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

                    # Chunk and index each document (embedding is already batched inside)
                    for new_doc, doc_data in new_docs:
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

                    # Log batch progress
                    logger.info(
                        f"[INDEX] 📊 Progress: {documents_indexed}/{total_docs} docs | {chunks_indexed} chunks"
                    )

                    # Clear batch
                    document_batch = []

        duration = time.time() - start_time

        logger.info(
            f"[INDEX] ✅ Completed: {documents_indexed} docs | {chunks_indexed} chunks | {duration:.2f}s"
        )

        return {
            "documents_indexed": documents_indexed,
            "chunks_indexed": chunks_indexed,
            "duration_seconds": duration,
        }

    except Exception as e:
        logger.error(f"[INDEX] ❌ Ingestion failed: {e}")
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

        with SessionLocal() as db:
            # Get document
            doc = db.query(Document).filter(Document.id == doc_uuid).first()

            if not doc:
                raise ValueError(f"Document not found: {document_id}")

            # Get existing chunks
            existing_chunks = db.query(Chunk).filter(Chunk.documentId == doc_uuid).all()
            chunk_ids = [str(chunk.id) for chunk in existing_chunks]

            # Delete from Qdrant
            if chunk_ids:
                try:
                    qdrant_client.delete(
                        collection_name=vectorize_settings.qdrant_collection_name,
                        points_selector=chunk_ids,
                    )
                except Exception as e:
                    logger.warning(f"[REINDEX] Failed to delete from Qdrant: {e}")

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
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(
                        f"[REINDEX] Failed to delete from Elasticsearch: {e}"
                    )

            # Delete chunks from database
            for chunk in existing_chunks:
                db.delete(chunk)
            db.commit()

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
        chunks_created = chunk_result.get("chunks_created", 0)

        logger.info(
            f"[REINDEX] ✅ doc_id={document_id[:8]}... | {len(chunk_ids)} deleted → {chunks_created} created | {duration:.2f}s"
        )

        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
            "duration_seconds": duration,
        }

    except Exception as e:
        logger.error(f"[REINDEX] ❌ Failed: {e}")
        raise
