"""track moderation_status — модерация загруженных треков (блок D)

Revision ID: 4f77633f0bf0
Revises: a367a749c438
Create Date: 2026-07-26 08:49:51.062409
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '4f77633f0bf0'
down_revision: str | None = 'a367a749c438'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('moderation_status', sa.String(length=16), server_default='approved', nullable=False)
        )
        batch_op.create_index(batch_op.f('ix_tracks_moderation_status'), ['moderation_status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tracks_moderation_status'))
        batch_op.drop_column('moderation_status')
