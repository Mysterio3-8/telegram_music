"""artists (сущности с фото) + tracks.cover_url (обложки в Mini App)

Revision ID: 8e5f9a2b3c4d
Revises: 7d4e8f1a2b3c
Create Date: 2026-07-23
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '8e5f9a2b3c4d'
down_revision: str | None = '7d4e8f1a2b3c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'artists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('normalized_name', sa.String(length=256), nullable=False),
        sa.Column('soundcloud_url', sa.String(length=512), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('normalized_name'),
    )
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cover_url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.drop_column('cover_url')
    op.drop_table('artists')
