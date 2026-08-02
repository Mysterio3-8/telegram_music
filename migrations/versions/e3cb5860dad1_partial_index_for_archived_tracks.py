"""Частичный индекс по архивным копиям треков (ускорение экрана /admin)

Экран /admin делал три запроса с условием storage_path IS NOT NULL, и каждый
шёл полным сканом таблицы tracks (133 МБ) ради 52 подходящих строк. На холодном
кэше это 2.9 сек на запрос — отсюда жалоба «бот тормозит» 2026-08-02.

Индекс частичный: NULL-ы (30 тысяч строк из 30 150) в него не попадают, поэтому
он занимает считанные килобайты вместо десятков мегабайт.

Revision ID: e3cb5860dad1
Revises: 0e5ddc09e7e6
Create Date: 2026-08-02 11:53:30.407402
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e3cb5860dad1'
down_revision: str | None = '0e5ddc09e7e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Намеренно без batch_alter_table: в SQLite он умеет пересоздавать таблицу
# копированием, а копировать 133 МБ на боксе с 961 МБ памяти незачем —
# CREATE INDEX эта СУБД выполняет напрямую.
_WHERE = sa.text("storage_path IS NOT NULL")


def upgrade() -> None:
    op.create_index(
        "ix_tracks_archived",
        "tracks",
        ["storage_path", "tg_file_id", "meta_synced", "file_size"],
        unique=False,
        sqlite_where=_WHERE,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_archived", table_name="tracks")
