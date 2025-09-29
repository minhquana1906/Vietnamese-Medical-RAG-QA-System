import uuid

from celery import shared_task
from loguru import logger

from .brain import (
    format_context,
    openai_chat_complete,
    openai_generate_embedding,
)
from .chunking import dynamic_chunking
from .config import DEFAULT_COLLECTION_NAME, EMBEDDING_MODEL, SYSTEM_PROMPT, TOP_K
from .database import get_celery_app
from .models import get_messages_from_conversation, update_conversation
from .summarizer import get_summarized_content
from .vectorize import search_vectors, upsert_points

celery_app = get_celery_app(__name__)
celery_app.autodiscover_tasks()


@shared_task
def chunk_and_index_document(doc_id, title, content):
    try:
        # Chunk the document
        nodes = dynamic_chunking(text=content, metadata={"doc_id": doc_id, "title": title})

        # Generate embeddings and prepare points for upsert
        points = []
        for node in nodes:
            embedding = openai_generate_embedding(node.text, model=EMBEDDING_MODEL)
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
        upsert_points(points, collection_name=DEFAULT_COLLECTION_NAME)
    except Exception as e:
        logger.error(f"Error in chunking and indexing document: {e}")
        raise


@shared_task
def rag_qa_task(history, question):
    try:
        # embedding question
        question_embedding = openai_generate_embedding(question, model=EMBEDDING_MODEL)
        logger.info(f"Generated embedding for question: {question_embedding[:50]}...")

        # retrieve top-k most relevant documents
        relevant_docs = search_vectors(
            query_vector=question_embedding,
            top_k=TOP_K,
            collection_name=DEFAULT_COLLECTION_NAME,
        )
        logger.info(f"Retrieved {len(relevant_docs)} relevant documents.\nDocs: {relevant_docs}")

        # format context from relevant documents
        formatted_context = format_context(relevant_docs)
        logger.info(f"Generated context from documents: {formatted_context}")

        # Build the message chain
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add history to the message chain
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the user's question to the message chain
        messages.append({
            "role": "user",
            "content": f"Dựa trên đoạn văn bản sau:\n{formatted_context}\nHãy trả lời câu hỏi sau:\n{question}\nNếu không tìm thấy thông tin trong đoạn văn bản, hãy trả lời lịch sự 'Xin lỗi, tôi không tìm thấy thông tin phù hợp cho câu hỏi: {question}.'",
        })

        response = openai_chat_complete(messages=messages, temperature=0.1, max_tokens=2048)
        logger.info(f"Generated RAG response: {response}")
        return response

    except Exception as e:
        logger.error(f"Error in RAG QA task: {e}")
        return "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."


@shared_task
def message_handler_task(bot_id, user_id, query):
    logger.info(f"Start handling message for bot {bot_id}, user {user_id}...")

    try:
        # add query message to db (mark as request)
        conversation_id = update_conversation(bot_id, user_id, query, is_request=True)

        messages = get_messages_from_conversation(conversation_id)
        logger.info(f"Retrieved {len(messages)} messages from conversation {conversation_id}")

        # get history of the conversation
        history = messages[:-1]

        # get answer from RAG
        answer = rag_qa_task(history, query)

        # summary answer message then add to db (mark as response and completed)
        summarized_answer = get_summarized_content(answer)
        update_conversation(bot_id, user_id, summarized_answer, is_request=False)

        logger.info(f"Completed handling message for bot {bot_id}, user {user_id}.")
        return {"role": "assistant", "content": answer}
    except Exception as e:
        logger.error(f"Error in message handler task: {e}")
    return {
        "role": "assistant",
        "content": "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi.",
    }
