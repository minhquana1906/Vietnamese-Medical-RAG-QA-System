from loguru import logger
from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, Enum,
                        Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.future import select
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .configs.setup import get_backend_settings
from .database import engine, get_db

settings = get_backend_settings()


Base: DeclarativeMeta = declarative_base()


class User(Base):

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    oauth_provider = Column(String(50), nullable=True)
    oauth_id = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, server_default="TRUE")
    user_metadata = Column(JSONB, server_default=func.jsonb_build_object())

    # Relationships
    chat_sessions = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}$'",
            name="email_format",
        ),
        CheckConstraint(
            "(password_hash IS NOT NULL) OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)",
            name="auth_method",
        ),
    )


class ChatSession(Base):

    __tablename__ = "chat_sessions"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    session_metadata = Column(JSONB, server_default=func.jsonb_build_object())
    is_active = Column(Boolean, server_default="TRUE")

    # Relationships
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "Message",
        back_populates="chat_session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):

    __tablename__ = "messages"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    chat_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(
        Enum("user", "assistant", "system", name="message_role"), nullable=False
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    message_metadata = Column(JSONB, server_default=func.jsonb_build_object())
    parent_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    chat_session = relationship("ChatSession", back_populates="messages")
    parent_message = relationship("Message", remote_side=[id], backref="child_messages")


class Chunk(Base):

    __tablename__ = "chunks"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False)
    overlap_start = Column(Integer, server_default="0")
    overlap_end = Column(Integer, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    chunk_metadata = Column(JSONB, server_default=func.jsonb_build_object())

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        CheckConstraint("chunk_index >= 0", name="valid_chunk_index"),
        CheckConstraint(
            "token_count > 0 AND token_count <= 512", name="valid_token_count"
        ),
    )


class FineTunedModel(Base):
    __tablename__ = "fine_tuned_models"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    model_name = Column(String(255), nullable=False)
    model_type = Column(
        Enum("generation", "embedding", "reranking", "guardrails", name="model_type"),
        nullable=False,
        index=True,
    )
    version = Column(String(100), nullable=False)
    huggingface_repo = Column(String(255), nullable=False)
    wandb_run_id = Column(String(255), nullable=True)
    training_dataset = Column(String(255), nullable=False)
    baseline_metrics = Column(JSONB, nullable=False)
    finetuned_metrics = Column(JSONB, nullable=False)
    improvement_pct = Column(Float, nullable=False)
    is_deployed = Column(Boolean, server_default="FALSE", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deployed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_model_name_version"),
        CheckConstraint(
            "is_deployed = FALSE OR improvement_pct >= 2.0", name="valid_improvement"
        ),
    )


class Document(Base):

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(255), nullable=True, index=True)
    doc_type = Column(
        Enum(
            "clinical_guideline",
            "drug_info",
            "medical_qa",
            "research_paper",
            "other",
            name="doc_type",
        ),
        nullable=True,
        index=True,
    )
    language = Column(String(2), server_default="vi")
    doc_metadata = Column(JSONB, server_default=func.jsonb_build_object())
    is_indexed = Column(Boolean, server_default="FALSE", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


# document's CRUD operations
def insert_document(title, content):
    with get_db() as db:
        new_doc = Document(title=title, content=content)
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        logger.info(f"Inserted document {new_doc.title} with ID: {new_doc.id}")
        return new_doc
