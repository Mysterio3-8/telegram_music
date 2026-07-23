"""tracks.artist_id — жёсткая привязка треков к артистам (SPEC-КАТАЛОГ §6)

Revision ID: 227271058451
Revises: 66dd24c3fa53
Create Date: 2026-07-23 23:16:19.917407
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '227271058451'
down_revision: str | None = '66dd24c3fa53'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('artist_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_tracks_artist_id'), ['artist_id'], unique=False)
        batch_op.create_foreign_key('fk_tracks_artist_id', 'artists', ['artist_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tracks_artist_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_tracks_artist_id'))
        batch_op.drop_column('artist_id')
