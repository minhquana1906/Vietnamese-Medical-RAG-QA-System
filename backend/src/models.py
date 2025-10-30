from loguru import logger
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.future import select
from sqlalchemy.sql import func

from .configs.setup import get_backend_settings
from .core.cache import get_conversation_id
from .database import engine, get_db

settings = get_backend_settings()


Base: DeclarativeMeta = declarative_base()


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(String(100), nullable=False, default="")
    bot_id = Column(String(100), nullable=False, default="Meddy")
    user_id = Column(String(100), nullable=False, default="user_1")
    message = Column(Text, nullable=False)
    is_request = Column(Boolean, nullable=False, default=True)
    is_completed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# Chat conversation's messages
def get_conversation_by_id(conversation_id):
    with get_db() as db:
        stmt = (
            select(ChatConversation)
            .where(ChatConversation.conversation_id == conversation_id)
            .order_by(ChatConversation.created_at.asc())
        )
        conversations = db.execute(stmt).scalars().all()
        # return rows with the same conversation's id. Each contains a message in the conversation
        if conversations:
            return conversations
        else:
            logger.warning(f"No conversation found with ID: {conversation_id}")
            return None


def update_conversation(bot_id, user_id, message, is_request=True):
    with get_db() as db:
        conversation_id = get_conversation_id(bot_id, user_id)
        if conversation_id:
            new_conversation = ChatConversation(
                conversation_id=conversation_id,
                bot_id=bot_id,
                user_id=user_id,
                message=message,
                is_request=is_request,
                is_completed=not is_request,
            )
            db.add(new_conversation)
            db.commit()
            db.refresh(new_conversation)
            return conversation_id


def convert_conversation_to_messages(conversation):
    messages = [{"role": "system", "content": settings.system_prompt}]

    for msg in conversation:
        role = "user" if msg.is_request else "assistant"
        messages.append({"role": role, "content": msg.message})

    return messages


def get_messages_from_conversation(conversation_id):
    conversation = get_conversation_by_id(conversation_id)
    if conversation:
        return convert_conversation_to_messages(conversation)


# document's CRUD operations
def insert_document(title, content):
    with get_db() as db:
        new_doc = Document(title=title, content=content)
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        logger.info(f"Inserted document {new_doc.title} with ID: {new_doc.id}")
        return new_doc
