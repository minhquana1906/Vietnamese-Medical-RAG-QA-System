from loguru import logger
from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
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
    """Chainlit User model - uses 'metadata_' to avoid SQLAlchemy reserved keyword"""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True)
    identifier = Column(Text, nullable=False, unique=True)
    metadata_ = Column("metadata", JSONB, nullable=False)  # DB column is 'metadata'
    createdAt = Column(Text, nullable=True)

    # Relationships
    threads = relationship(
        "Thread", back_populates="user", cascade="all, delete-orphan"
    )


class Thread(Base):
    """Chainlit Thread model - uses 'metadata_' to avoid SQLAlchemy reserved keyword"""

    __tablename__ = "threads"

    id = Column(UUID(as_uuid=True), primary_key=True)
    createdAt = Column(Text, nullable=True)
    name = Column(Text, nullable=True)
    userId = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    userIdentifier = Column(Text, nullable=True)
    tags = Column(ARRAY(Text), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)  # DB column is 'metadata'

    # Relationships
    user = relationship("User", back_populates="threads")
    steps = relationship("Step", back_populates="thread", cascade="all, delete-orphan")
    elements = relationship(
        "Element", back_populates="thread", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="thread", cascade="all, delete-orphan"
    )


class Step(Base):

    __tablename__ = "steps"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    threadId = Column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    parentId = Column(UUID(as_uuid=True), nullable=True)
    streaming = Column(Boolean, nullable=False)
    waitForAnswer = Column(Boolean, nullable=True)
    isError = Column(Boolean, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)  # DB column is 'metadata'
    tags = Column(ARRAY(Text), nullable=True)
    input = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    createdAt = Column(Text, nullable=True)
    command = Column(Text, nullable=True)
    start = Column(Text, nullable=True)
    end = Column(Text, nullable=True)
    generation = Column(JSONB, nullable=True)
    showInput = Column(Text, nullable=True)
    language = Column(Text, nullable=True)
    indent = Column(Integer, nullable=True)
    defaultOpen = Column(Boolean, nullable=True)

    # Relationships
    thread = relationship("Thread", back_populates="steps")


class Element(Base):

    __tablename__ = "elements"

    id = Column(UUID(as_uuid=True), primary_key=True)
    threadId = Column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=True
    )
    type = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    chainlitKey = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    display = Column(Text, nullable=True)
    objectKey = Column(Text, nullable=True)
    size = Column(Text, nullable=True)
    page = Column(Integer, nullable=True)
    language = Column(Text, nullable=True)
    forId = Column(UUID(as_uuid=True), nullable=True)
    mime = Column(Text, nullable=True)
    props = Column(JSONB, nullable=True)

    # Relationships
    thread = relationship("Thread", back_populates="elements")


class Feedback(Base):

    __tablename__ = "feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True)
    forId = Column(UUID(as_uuid=True), nullable=False)
    threadId = Column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    value = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)

    # Relationships
    thread = relationship("Thread", back_populates="feedbacks")


class Document(Base):
    """Document model - uses 'metadata_' to avoid SQLAlchemy reserved keyword"""

    __tablename__ = "documents"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)  # DB column is 'metadata'
    createdAt = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """Chunk model - uses 'metadata_' to avoid SQLAlchemy reserved keyword"""

    __tablename__ = "chunks"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    documentId = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunkIndex = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)  # DB column is 'metadata'
    createdAt = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("documentId", "chunkIndex", name="uq_document_chunk_index"),
    )


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.success("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


def insert_document(
    title: str,
    content: str,
    metadata: dict = None,
):
    with get_db() as db:
        new_doc = Document(
            title=title,
            content=content,
            metadata_=metadata or {},  # Use metadata_ (Python attribute)
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        logger.info(f"Inserted document '{new_doc.title}' with ID: {new_doc.id}")
        return new_doc
