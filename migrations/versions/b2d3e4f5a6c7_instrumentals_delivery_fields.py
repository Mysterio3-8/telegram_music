"""instrumentals delivery fields (tg_file_id, source, created_at)

Revision ID: b2d3e4f5a6c7
Revises: a1c2e3f4b5d6
Create Date: 2026-07-12 10:30:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d3e4f5a6c7'
down_revision: str | None = 'a1c2e3f4b5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('instrumentals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tg_file_id', sa.String(length=256), nullable=True))
        batch_op.add_column(
            sa.Column('source', sa.String(length=32), nullable=False, server_default='import')
        )
        batch_op.add_column(
            sa.Column(
                'created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('instrumentals', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('source')
        batch_op.drop_column('tg_file_id')
