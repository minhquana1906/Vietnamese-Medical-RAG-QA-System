from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7d5e3a8c9f2"
down_revision: Union[str, Sequence[str], None] = "9290fad6ca4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create custom ENUM types
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')")
    op.execute(
        "CREATE TYPE model_type AS ENUM ('generation', 'embedding', 'reranking', 'guardrails')"
    )
    op.execute(
        "CREATE TYPE doc_type AS ENUM ('clinical_guideline', 'drug_info', 'medical_qa', 'research_paper', 'other')"
    )

    # Create users table
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_id", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column(
            "user_metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")
        ),
        sa.CheckConstraint(
            "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}$'",
            name="email_format",
        ),
        sa.CheckConstraint(
            "(password_hash IS NOT NULL) OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)",
            name="auth_method",
        ),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index(
        "idx_users_oauth",
        "users",
        ["oauth_provider", "oauth_id"],
        postgresql_where=sa.text("oauth_provider IS NOT NULL"),
    )

    # Create chat_sessions table (threads)
    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "session_metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
    )
    op.create_index("idx_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index(
        "idx_chat_sessions_updated_at", "chat_sessions", [sa.text("updated_at DESC")]
    )

    # Create messages table (steps)
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "chat_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            postgresql.ENUM(
                "user", "assistant", "system", name="message_role", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "message_metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "parent_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_messages_session_id", "messages", ["chat_session_id"])
    op.create_index("idx_messages_created_at", "messages", ["created_at"])

    # Update documents table with enhanced metadata
    op.add_column("documents", sa.Column("source", sa.String(255), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "doc_type",
            postgresql.ENUM(
                "clinical_guideline",
                "drug_info",
                "medical_qa",
                "research_paper",
                "other",
                name="doc_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column("documents", sa.Column("language", sa.String(2), server_default="vi"))
    op.add_column(
        "documents",
        sa.Column(
            "doc_metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column(
        "documents",
        sa.Column("is_indexed", sa.Boolean, server_default=sa.text("FALSE")),
    )

    op.create_index("idx_documents_source", "documents", ["source"])
    op.create_index("idx_documents_type", "documents", ["doc_type"])
    op.create_index("idx_documents_indexed", "documents", ["is_indexed"])

    # Create chunks table
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("overlap_start", sa.Integer, server_default="0"),
        sa.Column("overlap_end", sa.Integer, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "chunk_metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunk_index"
        ),
        sa.CheckConstraint("chunk_index >= 0", name="valid_chunk_index"),
        sa.CheckConstraint(
            "token_count > 0 AND token_count <= 512", name="valid_token_count"
        ),
    )
    op.create_index("idx_chunks_document_id", "chunks", ["document_id"])
    op.create_index(
        "idx_chunks_document_index", "chunks", ["document_id", "chunk_index"]
    )

    # Create fine_tuned_models table
    op.create_table(
        "fine_tuned_models",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column(
            "model_type",
            postgresql.ENUM(
                "generation",
                "embedding",
                "reranking",
                "guardrails",
                name="model_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("huggingface_repo", sa.String(255), nullable=False),
        sa.Column("wandb_run_id", sa.String(255), nullable=True),
        sa.Column("training_dataset", sa.String(255), nullable=False),
        sa.Column("baseline_metrics", postgresql.JSONB, nullable=False),
        sa.Column("finetuned_metrics", postgresql.JSONB, nullable=False),
        sa.Column("improvement_pct", sa.Float, nullable=False),
        sa.Column("is_deployed", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("model_name", "version", name="uq_model_name_version"),
        sa.CheckConstraint(
            "is_deployed = FALSE OR improvement_pct >= 2.0", name="valid_improvement"
        ),
    )
    op.create_index("idx_fine_tuned_models_type", "fine_tuned_models", ["model_type"])
    op.create_index(
        "idx_fine_tuned_models_deployed", "fine_tuned_models", ["is_deployed"]
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("fine_tuned_models")
    op.drop_table("chunks")

    # Remove columns from documents table
    op.drop_index("idx_documents_indexed", "documents")
    op.drop_index("idx_documents_type", "documents")
    op.drop_index("idx_documents_source", "documents")
    op.drop_column("documents", "is_indexed")
    op.drop_column("documents", "doc_metadata")
    op.drop_column("documents", "language")
    op.drop_column("documents", "doc_type")
    op.drop_column("documents", "source")

    op.drop_table("messages")
    op.drop_table("chat_sessions")
    op.drop_table("users")

    # Drop custom ENUM types
    op.execute("DROP TYPE model_type")
    op.execute("DROP TYPE message_role")
    op.execute("DROP TYPE doc_type")
