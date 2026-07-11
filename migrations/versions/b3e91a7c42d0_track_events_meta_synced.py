"""track_events + tracks.meta_synced

Revision ID: b3e91a7c42d0
Revises: f87cfcd94b80
Create Date: 2026-07-11 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b3e91a7c42d0'
down_revision: str | None = 'f87cfcd94b80'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('meta_synced', sa.Boolean(), nullable=False, server_default='0')
        )

    op.create_table(
        'track_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('track_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_track_events_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_track_events_track_id'), ['track_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_track_events_event'), ['event'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('track_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_track_events_event'))
        batch_op.drop_index(batch_op.f('ix_track_events_track_id'))
        batch_op.drop_index(batch_op.f('ix_track_events_user_id'))
    op.drop_table('track_events')

    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.drop_column('meta_synced')
