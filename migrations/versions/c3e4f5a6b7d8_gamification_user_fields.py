"""gamification user fields (referred_by, referral_milestones_claimed, premium_discount_pct)

Revision ID: c3e4f5a6b7d8
Revises: b2d3e4f5a6c7
Create Date: 2026-07-14 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e4f5a6b7d8'
down_revision: str | None = 'b2d3e4f5a6c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referred_by', sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'referral_milestones_claimed',
                sa.Integer(),
                nullable=False,
                server_default='0',
            )
        )
        batch_op.add_column(
            sa.Column('premium_discount_pct', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.create_index('ix_users_referred_by', ['referred_by'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_referred_by')
        batch_op.drop_column('premium_discount_pct')
        batch_op.drop_column('referral_milestones_claimed')
        batch_op.drop_column('referred_by')
