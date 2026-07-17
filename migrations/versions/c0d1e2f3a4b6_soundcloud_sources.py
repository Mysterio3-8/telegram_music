"""soundcloud_sources: SoundCloud-профили как источники минусов с автопроверкой

Revision ID: c0d1e2f3a4b6
Revises: b9c0d1e2f3a5
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op

revision: str = "c0d1e2f3a4b6"
down_revision: str | None = "b9c0d1e2f3a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "soundcloud_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(length=512), nullable=False, unique=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("soundcloud_sources")
