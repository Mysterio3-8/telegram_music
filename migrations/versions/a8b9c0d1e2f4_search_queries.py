"""search_queries: реальные поисковые запросы Mini App (ТЗ §11)

Revision ID: a8b9c0d1e2f4
Revises: f6a7b8c9d0e2
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f4"
down_revision: str | None = "f6a7b8c9d0e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("query", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_search_queries_user_id", "search_queries", ["user_id"])
    op.create_index("ix_search_queries_query", "search_queries", ["query"])


def downgrade() -> None:
    op.drop_index("ix_search_queries_query", table_name="search_queries")
    op.drop_index("ix_search_queries_user_id", table_name="search_queries")
    op.drop_table("search_queries")
