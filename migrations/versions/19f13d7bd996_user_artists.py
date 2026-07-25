"""user_artists — подписка пользователя на артистов (референс «Мои артисты»)

Revision ID: 19f13d7bd996
Revises: 227271058451
Create Date: 2026-07-25 16:16:32.254810
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '19f13d7bd996'
down_revision: str | None = '227271058451'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_artists',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('artist_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'artist_id'),
    )
    with op.batch_alter_table('user_artists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_artists_artist_id'), ['artist_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('user_artists', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_artists_artist_id'))
    op.drop_table('user_artists')
