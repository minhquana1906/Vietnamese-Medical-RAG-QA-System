import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_chainlit_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("identifier", sa.Text, nullable=False, unique=True),
        sa.Column("user_metadata", postgresql.JSONB, nullable=False),
        sa.Column("createdAt", sa.Text, nullable=True),
    )

    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("createdAt", sa.Text, nullable=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column(
            "userId",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("userIdentifier", sa.Text, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("thread_metadata", postgresql.JSONB, nullable=True),
    )

    op.create_table(
        "steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column(
            "threadId",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parentId", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("streaming", sa.Boolean, nullable=False),
        sa.Column("waitForAnswer", sa.Boolean, nullable=True),
        sa.Column("isError", sa.Boolean, nullable=True),
        sa.Column("step_metadata", postgresql.JSONB, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("input", sa.Text, nullable=True),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column("createdAt", sa.Text, nullable=True),
        sa.Column("command", sa.Text, nullable=True),
        sa.Column("start", sa.Text, nullable=True),
        sa.Column("end", sa.Text, nullable=True),
        sa.Column("generation", postgresql.JSONB, nullable=True),
        sa.Column("showInput", sa.Text, nullable=True),
        sa.Column("language", sa.Text, nullable=True),
        sa.Column("indent", sa.Integer, nullable=True),
        sa.Column("defaultOpen", sa.Boolean, nullable=True),
    )

    op.create_table(
        "elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "threadId",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("type", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("chainlitKey", sa.Text, nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display", sa.Text, nullable=True),
        sa.Column("objectKey", sa.Text, nullable=True),
        sa.Column("size", sa.Text, nullable=True),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("language", sa.Text, nullable=True),
        sa.Column("forId", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mime", sa.Text, nullable=True),
        sa.Column("props", postgresql.JSONB, nullable=True),
    )

    op.create_table(
        "feedbacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("forId", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "threadId",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
    )

    # Create documents table (simple, essential attributes only)
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("document_metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "createdAt", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    # Create chunks table (simple, essential attributes only)
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "documentId",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunkIndex", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "createdAt", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    # Create indexes
    op.create_index("idx_chunks_document_id", "chunks", ["documentId"])

    # Create unique constraint for document + chunk index
    op.create_unique_constraint(
        "uq_document_chunk_index", "chunks", ["documentId", "chunkIndex"]
    )


def downgrade():
    op.drop_table("feedbacks")
    op.drop_table("elements")
    op.drop_table("steps")
    op.drop_table("threads")
    op.drop_table("users")
    op.drop_table("chunks")
    op.drop_table("documents")
