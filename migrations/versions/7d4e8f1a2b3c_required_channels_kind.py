"""required_channels.kind — «ОП на ботов»: кнопки-боты в гейте без проверки

Revision ID: 7d4e8f1a2b3c
Revises: 65379c6a0a2e
Create Date: 2026-07-23
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '7d4e8f1a2b3c'
down_revision: str | None = '65379c6a0a2e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('required_channels', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('kind', sa.String(length=16), server_default='channel', nullable=False)
        )
        batch_op.alter_column(
            'channel', existing_type=sa.String(length=128), type_=sa.String(length=256)
        )


def downgrade() -> None:
    with op.batch_alter_table('required_channels', schema=None) as batch_op:
        batch_op.alter_column(
            'channel', existing_type=sa.String(length=256), type_=sa.String(length=128)
        )
        batch_op.drop_column('kind')
