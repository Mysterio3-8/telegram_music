"""users.bot_blocked — рассылка: заблокировавшие бота выпадают из получателей

Revision ID: 9f2c2ce7f891
Revises: d1e2f3a4b5c7
Create Date: 2026-07-21
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9f2c2ce7f891'
down_revision: str | None = 'd1e2f3a4b5c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('bot_blocked', sa.Boolean(), server_default='0', nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('bot_blocked')
