"""track_events composite indexes — быстрая статистика без полного скана

Revision ID: 65379c6a0a2e
Revises: c0d77daffa52
Create Date: 2026-07-22
"""
from collections.abc import Sequence

from alembic import op


revision: str = '65379c6a0a2e'
down_revision: str | None = 'c0d77daffa52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('track_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_track_events_event'))
        batch_op.create_index('ix_track_events_user_event', ['user_id', 'event'], unique=False)
        batch_op.create_index(
            'ix_track_events_user_track_event', ['user_id', 'track_id', 'event'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('track_events', schema=None) as batch_op:
        batch_op.drop_index('ix_track_events_user_track_event')
        batch_op.drop_index('ix_track_events_user_event')
        batch_op.create_index(batch_op.f('ix_track_events_event'), ['event'], unique=False)
