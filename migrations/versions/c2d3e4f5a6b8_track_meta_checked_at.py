"""Отметка «метаданные этого трека уже сверяли с источником».

Без неё ночное дообогащение каждую ночь бралось бы за одни и те же треки: у
большинства альбома нет и не будет (сингл, фристайл, чужая перезаливка), и
такой трек вечно оставался бы «недообогащённым». Та же грабля, что с ремонтом
каталога в августе — там она стоила остановки всего ремонта.

Индекс частичный: у почти всего каталога тут NULL.

Revision ID: c2d3e4f5a6b8
Revises: b1c2d3e4f5a7
"""
import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b8"
down_revision = "b1c2d3e4f5a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("meta_checked_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_tracks_meta_checked",
        "tracks",
        ["meta_checked_at"],
        sqlite_where=sa.text("meta_checked_at IS NOT NULL"),
        postgresql_where=sa.text("meta_checked_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_meta_checked", table_name="tracks")
    op.drop_column("tracks", "meta_checked_at")
