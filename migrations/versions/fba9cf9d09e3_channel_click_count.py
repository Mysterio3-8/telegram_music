"""channel click_count — воронка кликов по каналам ОП (реклама)

Revision ID: fba9cf9d09e3
Revises: 6df6e521a5de
Create Date: 2026-07-25 23:44:55.104429
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'fba9cf9d09e3'
down_revision: str | None = '6df6e521a5de'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('required_channels', schema=None) as batch_op:
        batch_op.add_column(sa.Column('click_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('required_channels', schema=None) as batch_op:
        batch_op.drop_column('click_count')
