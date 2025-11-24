import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from ..configs.setup import get_backend_settings
from ..models import Step, Thread, User
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
            createdAt=datetime.now(timezone.utc).isoformat(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {user_identifier}")

    return user


def get_thread(db: Session, thread_id: str) -> Optional[Thread]:
    """Get thread by ID without creating it"""
    return db.query(Thread).filter(Thread.id == thread_id).first()


def get_or_create_thread(
    db: Session, thread_id: str, user_id: str, metadata: Optional[Dict] = None
) -> Thread:
    """
    Get thread by ID, create if not exists (for voice/audio inputs)

    Args:
        db: Database session
        thread_id: Thread UUID string
        user_id: User UUID (from get_or_create_user)
        metadata: Optional thread metadata

    Returns:
        Thread: Existing or newly created thread
    """
    thread = db.query(Thread).filter(Thread.id == thread_id).first()

    if not thread:
        thread = Thread(
            id=thread_id,
            userId=user_id,
            name="Voice Conversation",  # Default name for voice threads
            createdAt=datetime.now(timezone.utc).isoformat(),
            metadata_=metadata or {},
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
        logger.info(f"Created new thread: {thread_id} for user {user_id}")

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
    1. Get user (create if not exists)
    2. Get thread (must already exist from Chainlit)
    3. Get conversation history (Chainlit auto-saves messages)
    4. Call RAG pipeline
    5. Return response (Chainlit will save it)

    Args:
        db: Database session
        user_identifier: User identifier from OAuth
        thread_id: Thread UUID from Chainlit
        query: User's question

    Returns:
        Tuple[str, Optional[List[Dict]]]: (response_text, sources)
    """
    logger.info(f"Handling RAG query: user={user_identifier}, thread={thread_id}")

    # Get or create user
    user = get_or_create_user(db, user_identifier)
    if not user:
        logger.error(f"Failed to get/create user: {user_identifier}")
        return (
            "Xin lỗi, không thể xác thực người dùng. Vui lòng thử lại.",
            None,
        )

    # Get thread (must exist from Chainlit)
    thread = get_thread(db, thread_id)
    if not thread:
        logger.error(f"Thread {thread_id} not found. It should be created by Chainlit.")
        return (
            "❌ Không tìm thấy cuộc trò chuyện. Vui lòng làm mới trang và thử lại.",
            None,
        )

    # Get conversation history (excluding the current query as it hasn't been saved yet)
    history = get_conversation_history(db, thread)

    # Prepare messages for LLM (add system prompt)
    messages = prepare_messages_for_llm(history)

    # Extract history for RAG (exclude system prompt)
    # Include all history since Chainlit handles message saving
    rag_history = messages[1:] if len(messages) > 1 else []

    logger.info(f"Thread {thread.id}: {len(rag_history)} messages in history")

    # Call RAG pipeline
    try:
        response = bot_route_answer_message(rag_history, query)
        logger.info(f"Generated response for thread {thread.id}")

        # Safety check: handle None response
        if response is None:
            logger.error("RAG pipeline returned None - generation service unavailable")
            response = "Xin lỗi, hệ thống AI đang tạm thời không khả dụng. Vui lòng thử lại sau vài phút."
    except Exception as e:
        logger.error(f"Error in RAG pipeline: {e}", exc_info=True)
        response = "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."

    logger.info(f"RAG query completed: user={user_identifier}, thread={thread_id}")

    # TODO: Extract sources from RAG pipeline
    sources = None

    # Return response - Chainlit will automatically save both user message and assistant response
    return response, sources


def handle_speech_rag_query(
    db: Session, user_identifier: str, thread_id: str, query: str
) -> Tuple[str, Optional[List[Dict]]]:
    """
    Handle RAG query for Speech interface with optimized prompting.

    Uses SPEECH_RAG_SYSTEM_PROMPT for natural, concise audio-optimized responses.
    Same flow as handle_rag_query but with different system prompt.

    Args:
        db: Database session
        user_identifier: User identifier from OAuth
        thread_id: Thread UUID from Chainlit
        query: User's transcribed question

    Returns:
        Tuple[str, Optional[List[Dict]]]: (response_text, sources)
    """
    logger.info(
        f"Handling Speech RAG query: user={user_identifier}, thread={thread_id}"
    )

    # Get or create user
    user = get_or_create_user(db, user_identifier)
    if not user:
        logger.error(f"Failed to get/create user: {user_identifier}")
        return (
            "Xin lỗi, không thể xác thực người dùng. Vui lòng thử lại.",
            None,
        )

    # Get or create thread (auto-create for voice inputs)
    thread = get_or_create_thread(
        db, thread_id, str(user.id), metadata={"interface": "voice"}
    )

    if not thread:
        logger.error(f"Failed to get/create thread: {thread_id}")
        return (
            "Không tìm thấy cuộc trò chuyện. Vui lòng làm mới trang và thử lại.",
            None,
        )

    # Get conversation history
    history = get_conversation_history(db, thread)

    # Prepare messages with SPEECH-OPTIMIZED system prompt
    messages = [{"role": "system", "content": settings.speech_rag_system_prompt}]
    messages.extend(history)

    # Extract history for RAG (exclude system prompt)
    rag_history = messages[1:] if len(messages) > 1 else []

    logger.info(
        f"Speech RAG - Thread {thread.id}: {len(rag_history)} messages in history"
    )

    # Call RAG pipeline with speech-optimized prompt (PASS speech_rag_system_prompt)
    try:
        response = bot_route_answer_message(
            rag_history, query, system_prompt=settings.speech_rag_system_prompt
        )
        logger.info(f"Generated speech-optimized response for thread {thread.id}")

        # Safety check
        if response is None:
            logger.error(
                "Speech RAG pipeline returned None - generation service unavailable"
            )
            response = "Xin lỗi, hệ thống AI đang tạm thời không khả dụng. Vui lòng thử lại sau."
    except Exception as e:
        logger.error(f"Error in Speech RAG pipeline: {e}", exc_info=True)
        response = "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."

    logger.info(
        f"Speech RAG query completed: user={user_identifier}, thread={thread_id}"
    )

    # TODO: Extract sources from RAG pipeline
    sources = None

    return response, sources
