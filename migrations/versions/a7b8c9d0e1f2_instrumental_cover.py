"""Обложка и отметка дополнения у минусов

Минусы приезжают из ТГ-канала без обложки и часто без исполнителя («Неизвестный»
у 20 из 491 на 19.09) — в плеере это серая заглушка и пустая подпись. Ночная
задача ищет их в SoundCloud и дописывает недостающее.

`enrich_checked_at` — отметка «этим уже занимались», и ставится она КАЖДОМУ
тронутому минусу, даже если ничего не нашлось. Без такой отметки ночная работа
перебирает одно и то же и однажды останавливается, продолжая рапортовать —
ровно так было с ремонтом каталога (tracks.repair_checked_at, f1a2b3c4d5e6).

Revision ID: a7b8c9d0e1f2
Revises: 9c8d7e6f5a4b
"""
import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "9c8d7e6f5a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instrumentals", sa.Column("cover_url", sa.String(length=512), nullable=True))
    op.add_column("instrumentals", sa.Column("enrich_checked_at", sa.DateTime(), nullable=True))
    # Частичный индекс: у почти всех минусов тут NULL, и в индексе они не нужны
    op.create_index(
        "ix_instrumentals_enrich_checked_at",
        "instrumentals",
        ["enrich_checked_at"],
        sqlite_where=sa.text("enrich_checked_at IS NOT NULL"),
        postgresql_where=sa.text("enrich_checked_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_instrumentals_enrich_checked_at", table_name="instrumentals")
    op.drop_column("instrumentals", "enrich_checked_at")
    op.drop_column("instrumentals", "cover_url")
