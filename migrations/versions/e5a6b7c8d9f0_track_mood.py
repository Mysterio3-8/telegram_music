"""track mood field for recommendations

Revision ID: e5a6b7c8d9f0
Revises: d4f5a6b7c8e9
Create Date: 2026-07-14 00:20:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a6b7c8d9f0'
down_revision: str | None = 'd4f5a6b7c8e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mood', sa.String(length=16), nullable=True))
        batch_op.create_index('ix_tracks_mood', ['mood'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.drop_index('ix_tracks_mood')
        batch_op.drop_column('mood')
