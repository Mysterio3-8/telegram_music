"""soundcloud_imported: инкрементальный скан — не перекачивать известные ссылки

Revision ID: d1e2f3a4b5c7
Revises: c0d1e2f3a4b6
Create Date: 2026-07-18
"""
import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c7"
down_revision: str | None = "c0d1e2f3a4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "soundcloud_imported",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(length=512), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_soundcloud_imported_url", "soundcloud_imported", ["url"])


def downgrade() -> None:
    op.drop_index("ix_soundcloud_imported_url", table_name="soundcloud_imported")
    op.drop_table("soundcloud_imported")
