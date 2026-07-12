"""subscription_status

Revision ID: a1c2e3f4b5d6
Revises: 634a457eb4d6
Create Date: 2026-07-12 10:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c2e3f4b5d6'
down_revision: str | None = '634a457eb4d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'subscription_status',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=256), nullable=False),
        sa.Column('is_subscribed', sa.Boolean(), nullable=False),
        sa.Column('checked_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id', 'channel'),
    )


def downgrade() -> None:
    op.drop_table('subscription_status')
