"""telegram_channel_sources.target: канал может наполнять минусы, а не треки

Revision ID: b9c0d1e2f3a5
Revises: a8b9c0d1e2f4
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op

revision: str = "b9c0d1e2f3a5"
down_revision: str | None = "a8b9c0d1e2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telegram_channel_sources",
        sa.Column("target", sa.String(length=16), nullable=False, server_default="tracks"),
    )


def downgrade() -> None:
    op.drop_column("telegram_channel_sources", "target")
