"""payments log — лог выручки для статистики (блок E)

Revision ID: cd600706b345
Revises: 4f77633f0bf0
Create Date: 2026-07-26 09:04:38.427296
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'cd600706b345'
down_revision: str | None = '4f77633f0bf0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount_rub', sa.Integer(), server_default='0', nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('charge_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index('ix_payments_created', ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_user_id'))
        batch_op.drop_index('ix_payments_created')
    op.drop_table('payments')
