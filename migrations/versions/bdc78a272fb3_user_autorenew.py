"""user autorenew — автопродление Premium + сохранённый способ оплаты (блок E)

Revision ID: bdc78a272fb3
Revises: cd600706b345
Create Date: 2026-07-26 09:11:38.645142
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'bdc78a272fb3'
down_revision: str | None = 'cd600706b345'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('autorenew', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('pay_method_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('pay_method_id')
        batch_op.drop_column('autorenew')
