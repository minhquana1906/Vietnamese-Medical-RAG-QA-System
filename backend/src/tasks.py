import uuid

from celery import shared_task
from loguru import logger

from .brain import (format_context, openai_chat_complete,
                    openai_generate_embedding)
from .chunking import dynamic_chunking
from .config import get_backend_settings
from .database import get_celery_app
from .models import get_messages_from_conversation, update_conversation
from .rerank import rerank_documents
from .summarizer import get_summarized_content
from .vectorize import search_vectors, upsert_points

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

        # Generate embeddings and prepare points for upsert
        points = []
        for node in nodes:
            embedding = openai_generate_embedding(
                node.text, model=settings.openai_embedding_model
            )
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
        upsert_points(points, collection_name=settings.default_collection_name)
    except Exception as e:
        logger.error(f"Error in chunking and indexing document: {e}")
        raise


@shared_task
def rag_qa_task(history, question):
    try:
        # Generate embedding for question
        question_embedding = openai_generate_embedding(
            question, model=settings.openai_embedding_model
        )

        # Retrieve top-k most relevant documents
        relevant_docs = search_vectors(
            query_vector=question_embedding,
            top_k=settings.top_k,
            collection_name=settings.default_collection_name,
        )
        logger.info(f"Retrieved {len(relevant_docs)} documents from vector DB")

        # rerank
        reranked_docs = rerank_documents(question, relevant_docs)

        # Format context from relevant documents
        formatted_context = format_context(reranked_docs)

        # Build the message chain
        messages = [{"role": "system", "content": settings.system_prompt}]

        # Add history to the message chain
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the user's question to the message chain
        messages.append(
            {
                "role": "user",
                "content": settings.rag_prompt.format(
                    context=formatted_context, question=question
                ),
            }
        )

        response = openai_chat_complete(
            messages=messages, temperature=0.1, max_tokens=2048
        )
        logger.info(f"✓ RAG response generated successfully")
        return response

    except Exception as e:
        logger.error(f"Error in RAG QA task: {e}")
        return "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."


@shared_task
def message_handler_task(bot_id, user_id, query):
    logger.info(f"Message handler started: {bot_id}/{user_id}")

    try:
        # Add query message to db (mark as request)
        conversation_id = update_conversation(bot_id, user_id, query, is_request=True)

        # Retrieve conversation history
        messages = get_messages_from_conversation(conversation_id)
        logger.info(
            f"Conversation {conversation_id}: {len(messages)} messages in history"
        )

        # Get answer from RAG
        answer = rag_qa_task(messages[:-1], query)
        logger.info(
            f"Generated RAG response for conversation {conversation_id}:\n{answer}"
        )

        # Summarize and save the response
        summarized_answer = get_summarized_content(answer)
        update_conversation(bot_id, user_id, summarized_answer, is_request=False)

        logger.info(f"Message handler completed: {bot_id}/{user_id}")

        return {"role": "assistant", "content": answer}
    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        return {
            "role": "assistant",
            "content": "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi.",
        }
