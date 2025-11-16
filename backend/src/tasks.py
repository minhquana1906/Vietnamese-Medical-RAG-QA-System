import uuid

from celery import shared_task
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
from .services.chunking import dynamic_chunking
from .services.embedding import get_embedding_service
from .services.rerank import get_qwen3_reranker
from .core.guardrails import get_guardrails_service

settings = get_backend_settings()

celery_app = get_celery_app(__name__)
celery_app.autodiscover_tasks()


@shared_task
def chunk_and_index_document(doc_id, title, content):
    try:
        # Chunk the document
        nodes = dynamic_chunking(
            text=content, metadata={"doc_id": doc_id, "title": title}
        )

        # Get embedding service
        embedding_service = get_embedding_service()

        # Generate embeddings and prepare points for upsert
        points = []
        for node in nodes:
            # Use Qwen3 embedding service
            embedding = embedding_service.embed_text(node.text, use_cache=False)
            if not embedding:
                logger.warning(
                    f"Failed to generate embedding for chunk: {node.text[:50]}..."
                )
                continue

            point = {
                "id": str(uuid.uuid4()),
                "embedding": embedding,
                "metadata": {
                    "doc_id": doc_id,
                    "title": title,
                    "content": node.text,
                },
            }
            points.append(point)

        # Upsert points to Qdrant vector database
        if points:
            upsert_points(points, collection_name=settings.default_collection_name)
            logger.info(f"Indexed {len(points)} chunks for document '{title}'")
        else:
            logger.warning(f"No embeddings generated for document '{title}'")
    except Exception as e:
        logger.error(f"Error in chunking and indexing document: {e}")
        raise


@shared_task()
def bot_route_answer_message(history, question):
    # detect the route
    route = detect_route(history, question)
    logger.info(f"Bot route: {route}")
    if route == "medical":
        return rag_qa_task(history, question)
    elif route == "general":
        return ai_agent_handle(question)


@shared_task
def rag_qa_task(history, question):
    """
    RAG QA task with Qwen3Guard input/output validation.

    Flow:
    1. Validate user input with Qwen3Guard
    2. If valid, proceed with RAG pipeline
    3. Generate response with Qwen3
    4. Validate response with Qwen3Guard
    5. If invalid, regenerate with feedback (max 2 retries)
    6. Return final validated response
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

        # Generate embedding for question using Qwen3
        logger.info("🔢 Generating embedding with Qwen3-Embedding...")
        question_embedding = embedding_service.embed_text(new_question, use_cache=True)

        if not question_embedding:
            logger.error("❌ Failed to generate embedding for question")
            return "Xin lỗi, không thể xử lý câu hỏi của bạn lúc này."

        # Retrieve top-k most relevant documents
        logger.info(f"🔎 Searching vector database (top_k={settings.top_k})...")
        relevant_docs = search_vectors(
            query_vector=question_embedding,
            top_k=settings.top_k,
            collection_name=settings.default_collection_name,
        )
        logger.info(f"📚 Retrieved {len(relevant_docs)} documents from vector DB")

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

        # Build the message chain
        messages = [{"role": "system", "content": settings.system_prompt}]

        # Add history to the message chain
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        max_retries = 2
        retry_count = 0
        final_response = None

        while retry_count <= max_retries:
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

                # Use Qwen3 generation model
                response = qwen3_chat_complete(
                    messages=messages_with_query,
                    temperature=0.7,
                    max_tokens=2048,
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

    except Exception as e:
        logger.error(f"❌ Error in RAG QA task: {e}", exc_info=True)
        raise
