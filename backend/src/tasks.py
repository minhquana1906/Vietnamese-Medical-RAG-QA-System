import uuid

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from .configs.celery_config import get_celery_app
from .configs.setup import get_backend_settings
from .core.vectorize import search_vectors, upsert_points
from .services.agent import ai_agent_handle
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
def chunk_and_index_document(doc_id, title, content):
    """
    Chunk document and index to both Qdrant (vector) and Elasticsearch (keyword).

    This implements dual indexing strategy (T088) for hybrid search:
    1. Chunk document using fixed semantic strategy
    2. Generate embeddings for each chunk
    3. Index to Qdrant (vector search)
    4. Index to Elasticsearch (keyword search)

    Args:
        doc_id: Document ID
        title: Document title
        content: Document content
    """
    try:
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

        for chunk_index, node in enumerate(nodes):
            # Use Qwen3 embedding service for documents (NO instruction prefix)
            embedding = embedding_service.embed_document(node.text)
            if not embedding:
                logger.warning(
                    f"Failed to generate embedding for chunk {chunk_index}: {node.text[:50]}..."
                )
                continue

            # Generate unique chunk ID
            chunk_id = str(uuid.uuid4())

            # Prepare Qdrant point (vector search)
            qdrant_point = {
                "id": chunk_id,
                "embedding": embedding,
                "metadata": {
                    "doc_id": doc_id,
                    "title": title,
                    "content": node.text,
                    "chunk_index": chunk_index,
                    "doc_type": "medical_qa",  # Can be parameterized later
                    "source": "",  # Can be added from metadata
                },
            }
            qdrant_points.append(qdrant_point)

            # Prepare Elasticsearch document (keyword search)
            # Note: Elasticsearch indexing happens separately per document
            elasticsearch_docs.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "chunk_index": chunk_index,
                    "content": node.text,
                    "title": title,
                }
            )

        # Index to Qdrant (vector database)
        if qdrant_points:
            upsert_points(
                qdrant_points, collection_name=settings.default_collection_name
            )
            logger.info(f"✅ Indexed {len(qdrant_points)} chunks to Qdrant")
        else:
            logger.warning(f"⚠️ No embeddings generated for document '{title}'")

        # Index to Elasticsearch (keyword search)
        if elasticsearch_docs:
            indexed_count = 0
            for es_doc in elasticsearch_docs:
                success = es_client.index_chunk(
                    chunk_id=es_doc["chunk_id"],
                    document_id=es_doc["document_id"],
                    chunk_index=es_doc["chunk_index"],
                    content=es_doc["content"],
                    title=es_doc["title"],
                    doc_type="medical_qa",
                    source="",
                    language="vi",
                    metadata={"doc_id": doc_id},
                )
                if success:
                    indexed_count += 1

            logger.info(
                f"✅ Indexed {indexed_count}/{len(elasticsearch_docs)} chunks to Elasticsearch"
            )

        logger.info(
            f"🎉 Dual indexing complete for document '{title}': "
            f"{len(qdrant_points)} chunks → Qdrant (vector) + Elasticsearch (keyword)"
        )

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
        return qwen3_chat_complete(
            messages=history + [{"role": "user", "content": question}],
            temperature=0.7,
            max_tokens=1024,
            use_fallback=False,
        )


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

        # Add history with automatic summarization if too long
        # Target: ~2000 tokens for history (8000 chars) to leave room for:
        # - Context: ~1000 tokens (RAG or Tavily)
        # - System prompt: ~200 tokens
        # - Generation: ~2048 tokens
        # Total: ~5248 tokens (well under 8192 limit)
        history_with_system = messages + history
        optimized_history = summarize_old_messages(
            history_with_system, target_tokens=2000
        )
        messages = optimized_history

        max_retries = 2
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
