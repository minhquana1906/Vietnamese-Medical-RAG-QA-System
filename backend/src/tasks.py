import uuid

from celery import shared_task
from loguru import logger

from .configs.celery_config import get_celery_app
from .configs.setup import get_backend_settings
from .core.vectorize import search_vectors, upsert_points
from .database import SessionLocal
from .models import ChatSession, Message, User
from .services.agent import ai_agent_handle
from .services.brain import (detect_route, enhance_query_quality,
                             get_tavily_agent_answer, openai_chat_complete,
                             openai_generate_embedding)
from .services.chunking import dynamic_chunking
from .services.rerank import cohere_rerank
from .services.summarizer import get_summarized_content

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
    try:
        new_question = enhance_query_quality(history, question)
        # Generate embedding for question
        question_embedding = openai_generate_embedding(
            new_question, model=settings.openai_embedding_model
        )

        # Retrieve top-k most relevant documents
        relevant_docs = search_vectors(
            query_vector=question_embedding,
            top_k=settings.top_k,
            collection_name=settings.default_collection_name,
        )
        logger.info(f"Retrieved {len(relevant_docs)} documents from vector DB")

        # rerank
        if relevant_docs:
            reranked_docs, rerank_context = cohere_rerank(new_question, relevant_docs)
        else:
            reranked_docs, rerank_context = None, None

        # Check if RAG results have sufficient confidence. If best score is too low, use web search
        use_web_search = False
        if not reranked_docs or (
            reranked_docs and reranked_docs[0].relevance_score < 0.5
        ):
            logger.info(
                f"RAG confidence low (best score: {reranked_docs[0].relevance_score if reranked_docs else 0}), will use web search as fallback"
            )
            use_web_search = True

        formatted_context = (
            rerank_context
            if reranked_docs
            else "Can't find relevant documents from knowledge base."
        )

        # Build the message chain
        messages = [{"role": "system", "content": settings.system_prompt}]

        # Add history to the message chain
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        if use_web_search:
            # Use web search with Tavily agent
            messages.append(
                {
                    "role": "user",
                    "content": f"RAG Context (can be insufficient):\n{formatted_context}\n\nQuestion: {new_question}\n\nNote: Information in RAG context may be insufficient. Please search for additional information from the internet and ALWAYS provide the source with the full URL.",
                }
            )

            response = get_tavily_agent_answer(messages)
            logger.info("Response generated with web search fallback")
        else:
            # Use standard RAG response
            messages.append(
                {
                    "role": "user",
                    "content": settings.rag_prompt.format(
                        context=formatted_context, question=new_question
                    ),
                }
            )
            response = openai_chat_complete(
                messages=messages, temperature=0.7, max_tokens=2048
            )
            logger.info("RAG response generated successfully")

        return response

    except Exception as e:
        logger.error(f"Error in RAG QA task: {e}")
        raise


@shared_task
def message_handler_task(bot_id, user_id, query):
    logger.info(f"Message handler started: {bot_id}/{user_id}")

    try:
        with SessionLocal() as db:
            # Create or get chat session for this user
            # Note: In the new schema, user_id should be a UUID from the users table
            # For now, we'll use bot_id as a fallback identifier until proper user authentication is implemented

            # Try to find existing active session
            chat_session = (
                db.query(ChatSession)
                .join(User)
                .filter(
                    User.oauth_id
                    == user_id,  # Using oauth_id as temporary user identifier
                    ChatSession.is_active == True,
                )
                .first()
            )

            # If no session exists, create a default user and session
            if not chat_session:
                # Check if user exists
                user = db.query(User).filter(User.oauth_id == user_id).first()

                if not user:
                    # Create default user for legacy bot interactions
                    import uuid as uuid_lib

                    user = User(
                        id=uuid_lib.uuid4(),
                        email=f"{user_id}@legacy.local",
                        oauth_provider="legacy",
                        oauth_id=user_id,
                        display_name=f"Legacy User {user_id}",
                        is_active=True,
                        user_metadata={"bot_id": bot_id, "legacy": True},
                    )
                    db.add(user)
                    db.flush()

                # Create new chat session
                chat_session = ChatSession(
                    user_id=user.id,
                    name=f"Chat with {bot_id}",
                    is_active=True,
                    session_metadata={"bot_id": bot_id},
                )
                db.add(chat_session)
                db.flush()

            # Add user message
            user_message = Message(
                chat_session_id=chat_session.id,
                role="user",
                content=query,
            )
            db.add(user_message)
            db.commit()

            # Get conversation history
            messages_db = (
                db.query(Message)
                .filter(Message.chat_session_id == chat_session.id)
                .order_by(Message.created_at)
                .all()
            )

            # Convert to format expected by LLM
            messages = [{"role": "system", "content": settings.system_prompt}]
            for msg in messages_db:
                messages.append({"role": msg.role, "content": msg.content})

            logger.info(
                f"Session {chat_session.id}: {len(messages)} messages in history"
            )

            # Get answer from RAG (history excludes the current query)
            history = messages[:-1]
            answer = bot_route_answer_message(history, query)
            logger.info(f"Generated response for session {chat_session.id}:\n{answer}")

            # Summarize and save the response
            summarized_answer = get_summarized_content(answer)

            assistant_message = Message(
                chat_session_id=chat_session.id,
                role="assistant",
                content=summarized_answer,
            )
            db.add(assistant_message)
            db.commit()

            logger.info(f"Message handler completed: {bot_id}/{user_id}")

            return {"role": "assistant", "content": answer}

    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        return {
            "role": "assistant",
            "content": "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi.",
        }
