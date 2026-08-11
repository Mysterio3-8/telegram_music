"""tracks.source_url — ссылка источника, откуда приехал трек

Нужна как точный ключ «этот кандидат из поисковой выдачи у нас уже есть».
Сверка по «исполнитель — название» промахивалась: в выдаче заголовок один, а в
скачанном файле другой, поэтому бот заново качал уже залитый трек — лишние
секунды ожидания, а на DRM-копии ещё и ложное «трек под защитой» (жалоба
владельца 11.08: «ругается, хотя до этого мне качал его»).

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("source_url", sa.String(length=512), nullable=True))
    # Частичный индекс: у 30 тысяч старых треков ссылки нет, индексировать NULL-ы
    # незачем — так же сделан ix_tracks_archived (миграция e3cb5860dad1).
    op.create_index(
        "ix_tracks_source_url",
        "tracks",
        ["source_url"],
        unique=False,
        sqlite_where=sa.text("source_url IS NOT NULL"),
        postgresql_where=sa.text("source_url IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_source_url", table_name="tracks")
    op.drop_column("tracks", "source_url")
