import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from ..configs.setup import get_backend_settings
from ..models import Step, Thread, User
from ..services.summarizer import get_summarized_content
from ..tasks import bot_route_answer_message

settings = get_backend_settings()


def get_or_create_user(
    db: Session, user_identifier: str, metadata: Optional[Dict] = None
) -> User:
    user = db.query(User).filter(User.identifier == user_identifier).first()

    if not user:
        user = User(
            id=uuid_lib.uuid4(),
            identifier=user_identifier,
            metadata_=metadata or {},
            createdAt=datetime.now(timezone.utc).isoformat(),  # Set proper timestamp
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {user_identifier}")

    return user


def get_or_create_thread(
    db: Session,
    thread_id: str,
    user: User,
    thread_name: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Thread:
    thread = db.query(Thread).filter(Thread.id == thread_id).first()

    if not thread:
        thread = Thread(
            id=thread_id,
            userId=user.id,
            userIdentifier=user.identifier,
            name=thread_name,
            createdAt=datetime.now(timezone.utc).isoformat(),
            metadata_=metadata or {},
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
        logger.info(f"Created new thread: {thread_id} for user: {user.identifier}")

    return thread


def save_user_message(db: Session, thread: Thread, query: str) -> Step:
    user_step = Step(
        id=uuid_lib.uuid4(),
        name="user_message",
        type="user_message",
        threadId=thread.id,
        streaming=False,
        input=query,
        output=query,
        createdAt=datetime.now(timezone.utc).isoformat(),
        metadata_={"role": "user"},
    )
    db.add(user_step)
    db.commit()
    db.refresh(user_step)
    logger.debug(f"Saved user message to thread {thread.id}")
    return user_step


def save_assistant_message(
    db: Session, thread: Thread, query: str, response: str, summarized_response: str
) -> Step:
    assistant_step = Step(
        id=uuid_lib.uuid4(),
        name="assistant_message",
        type="assistant_message",
        threadId=thread.id,
        streaming=False,
        input=query,
        output=summarized_response,
        createdAt=datetime.now(timezone.utc).isoformat(),
        metadata_={"role": "assistant", "full_response_length": len(response)},
    )
    db.add(assistant_step)
    db.commit()
    db.refresh(assistant_step)
    logger.debug(f"Saved assistant message to thread {thread.id}")
    return assistant_step


def get_conversation_history(db: Session, thread: Thread) -> List[Dict[str, str]]:
    previous_steps = (
        db.query(Step)
        .filter(Step.threadId == thread.id)
        .filter(Step.type.in_(["user_message", "assistant_message"]))
        .order_by(Step.createdAt)
        .all()
    )

    messages = []
    for step in previous_steps:
        # Determine role from step metadata or type
        role = step.metadata_.get("role", "user") if step.metadata_ else "user"
        if step.type == "assistant_message":
            role = "assistant"

        content = step.output if step.output else step.input
        if content:
            messages.append({"role": role, "content": content})

    logger.debug(f"Retrieved {len(messages)} messages from thread {thread.id}")
    return messages


def prepare_messages_for_llm(
    history: List[Dict[str, str]], system_prompt: Optional[str] = None
) -> List[Dict[str, str]]:
    prompt = system_prompt or settings.system_prompt
    messages = [{"role": "system", "content": prompt}]
    messages.extend(history)
    return messages


def handle_rag_query(
    db: Session, user_identifier: str, thread_id: str, query: str
) -> Tuple[str, Optional[List[Dict]]]:
    """
    Handle complete RAG query flow:
    1. Get/create user and thread
    2. Save user message
    3. Get conversation history
    4. Call RAG pipeline
    5. Save assistant response

    Args:
        db: Database session
        user_identifier: User identifier from OAuth
        thread_id: Thread UUID
        query: User's question

    Returns:
        Tuple[str, Optional[List[Dict]]]: (response_text, sources)
    """
    logger.info(f"Handling RAG query: user={user_identifier}, thread={thread_id}")

    user = get_or_create_user(db, user_identifier)

    if not user:
        logger.error(f"Failed to get/create user: {user_identifier}")
        return (
            "Xin lỗi, không thể xác thực người dùng. Vui lòng thử lại.",
            None,
        )

    thread = get_or_create_thread(db, thread_id, user)

    save_user_message(db, thread, query)

    history = get_conversation_history(db, thread)

    messages = prepare_messages_for_llm(history)

    # Extract history for RAG (exclude system prompt and current query)
    # Since we saved user message, we need to exclude the last message
    rag_history = messages[1:-1] if len(messages) > 1 else []

    logger.info(f"Thread {thread.id}: {len(rag_history)} messages in history")

    # Call RAG pipeline
    try:
        response = bot_route_answer_message(rag_history, query)
        logger.info(f"Generated response for thread {thread.id}")
    except Exception as e:
        logger.error(f"Error in RAG pipeline: {e}")
        response = "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."

    # Summarize and save assistant response
    summarized_response = get_summarized_content(response)
    save_assistant_message(db, thread, query, response, summarized_response)

    logger.info(f"RAG query completed: user={user_identifier}, thread={thread_id}")

    # TODO: Extract sources from RAG pipeline
    sources = None

    return response, sources
