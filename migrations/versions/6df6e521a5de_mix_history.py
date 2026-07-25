"""mix_history — что TG Микс уже показывал (антиповтор)

Revision ID: 6df6e521a5de
Revises: 19f13d7bd996
Create Date: 2026-07-25 16:38:26.755417
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '6df6e521a5de'
down_revision: str | None = '19f13d7bd996'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'mix_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mix_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mix_history_track_id'), ['track_id'], unique=False)
        batch_op.create_index('ix_mix_history_user_created', ['user_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_mix_history_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('mix_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mix_history_user_id'))
        batch_op.drop_index('ix_mix_history_user_created')
        batch_op.drop_index(batch_op.f('ix_mix_history_track_id'))
    op.drop_table('mix_history')
