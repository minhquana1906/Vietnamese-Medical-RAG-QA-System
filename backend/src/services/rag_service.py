import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from ..configs.logging_config import get_rag_logger
from ..configs.setup import get_backend_settings
from ..models import Step, Thread, User
from ..tasks import bot_route_answer_message

settings = get_backend_settings()
rag_log = get_rag_logger()


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

    return user


def get_thread(db: Session, thread_id: str) -> Optional[Thread]:
    """Get thread by ID without creating it"""
    return db.query(Thread).filter(Thread.id == thread_id).first()


def get_or_create_thread(
    db: Session, thread_id: str, user_id: str, metadata: Optional[Dict] = None
) -> Thread:
    """Get thread by ID, create if not exists (for voice/audio inputs)"""
    thread = db.query(Thread).filter(Thread.id == thread_id).first()

    if not thread:
        thread = Thread(
            id=thread_id,
            userId=user_id,
            name="Voice Conversation",
            createdAt=datetime.now(timezone.utc).isoformat(),
            metadata_=metadata or {},
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)

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
    """
    import time

    request_start = time.time()

    rag_log.log_request_start(user_identifier, thread_id, query)

    # Get or create user
    user = get_or_create_user(db, user_identifier)
    if not user:
        logger.error(f"[RAG] User creation failed: {user_identifier}")
        return (
            "Xin lỗi, không thể xác thực người dùng. Vui lòng thử lại.",
            None,
        )

    # Get or create thread (auto-create for API/Locust usage)
    thread = get_or_create_thread(db, thread_id, str(user.id))

    if not thread:
        logger.error(f"[RAG] Thread creation failed: {thread_id}")
        return (
            "❌ Không thể tạo cuộc trò chuyện. Vui lòng thử lại.",
            None,
        )

    # Get conversation history
    history = get_conversation_history(db, thread)
    messages = prepare_messages_for_llm(history)
    rag_history = messages[1:] if len(messages) > 1 else []

    # Call RAG pipeline
    try:
        response = bot_route_answer_message(rag_history, query)

        if response is None:
            logger.error("[RAG] Pipeline returned None")
            response = "Xin lỗi, hệ thống AI đang tạm thời không khả dụng. Vui lòng thử lại sau vài phút."
    except Exception as e:
        logger.error(f"[RAG] Pipeline error: {e}", exc_info=True)
        response = "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."

    rag_log.log_request_complete(request_start, success=True)
    sources = None
    return response, sources


def handle_speech_rag_query(
    db: Session, user_identifier: str, thread_id: str, query: str
) -> Tuple[str, Optional[List[Dict]]]:
    """
    Handle RAG query for Speech interface with optimized prompting.
    Uses SPEECH_RAG_SYSTEM_PROMPT for natural, concise audio-optimized responses.
    """
    import time

    request_start = time.time()

    rag_log.log_request_start(user_identifier, thread_id, query)

    # Get or create user
    user = get_or_create_user(db, user_identifier)
    if not user:
        logger.error(f"[RAG] User creation failed: {user_identifier}")
        return (
            "Xin lỗi, không thể xác thực người dùng. Vui lòng thử lại.",
            None,
        )

    # Get or create thread (auto-create for voice inputs)
    thread = get_or_create_thread(
        db, thread_id, str(user.id), metadata={"interface": "voice"}
    )

    if not thread:
        logger.error(f"[RAG] Thread creation failed: {thread_id}")
        return (
            "Không tìm thấy cuộc trò chuyện. Vui lòng làm mới trang và thử lại.",
            None,
        )

    # Get conversation history
    history = get_conversation_history(db, thread)
    messages = [{"role": "system", "content": settings.speech_rag_system_prompt}]
    messages.extend(history)
    rag_history = messages[1:] if len(messages) > 1 else []

    # Call RAG pipeline with speech-optimized prompt
    try:
        response = bot_route_answer_message(
            rag_history, query, system_prompt=settings.speech_rag_system_prompt
        )

        if response is None:
            logger.error("[RAG] Speech pipeline returned None")
            response = "Xin lỗi, hệ thống AI đang tạm thời không khả dụng. Vui lòng thử lại sau."
    except Exception as e:
        logger.error(f"[RAG] Speech pipeline error: {e}", exc_info=True)
        response = "Xin lỗi, đã có lỗi xảy ra trong quá trình xử lý câu hỏi."

    rag_log.log_request_complete(request_start, success=True)
    sources = None
    return response, sources
