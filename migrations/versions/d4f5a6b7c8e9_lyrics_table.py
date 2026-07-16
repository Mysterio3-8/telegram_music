"""lyrics table

Revision ID: d4f5a6b7c8e9
Revises: c3e4f5a6b7d8
Create Date: 2026-07-14 00:10:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f5a6b7c8e9'
down_revision: str | None = 'c3e4f5a6b7d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'lyrics',
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='user'),
        sa.Column(
            'updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False
        ),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id']),
        sa.PrimaryKeyConstraint('track_id'),
    )


def downgrade() -> None:
    op.drop_table('lyrics')
