"""required_channels table + seed from env (управление подпиской из админки)

Revision ID: f6a7b8c9d0e2
Revises: e5a6b7c8d9f0
Create Date: 2026-07-17 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e2'
down_revision: str | None = 'e5a6b7c8d9f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        'required_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=128), nullable=False),
        sa.Column('label', sa.String(length=128), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel'),
    )
    # Переносим каналы из .env — поведение гейта не меняется при деплое
    from app.config import settings

    rows = [
        {"channel": channel, "label": label} for channel, label in settings.required_channels
    ]
    if rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    op.drop_table('required_channels')
