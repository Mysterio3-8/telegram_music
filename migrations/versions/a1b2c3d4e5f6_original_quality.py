"""Оригинальное качество: файл автора у трека + выбор формата у пользователя

SoundCloud отдаёт исходный файл, загруженный автором (часто WAV или FLAC), если
тот разрешил скачивание. Мы про этот путь не знали и всегда брали поток
128 kbps — а именно на качестве конкуренты строят платные тарифы.

Оригинал живёт ПОЛЯМИ существующего трека, а не отдельной строкой в tracks:
это один и тот же трек. Вторая запись раздвоила бы его в библиотеке, плейлистах,
поиске и статистике, а дедуп начал бы считать две наши записи дубликатами.

Revision ID: a1b2c3d4e5f6
Revises: c7d8e9f0a1b2
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hq_file_id — идентификатор ДОКУМЕНТА, не аудио: Bot API показывает в плеере
    # только mp3 и m4a, WAV/FLAC уходят файлом и пересылаются send_document.
    op.add_column("tracks", sa.Column("hq_file_id", sa.String(length=256), nullable=True))
    op.add_column("tracks", sa.Column("hq_format", sa.String(length=8), nullable=True))
    op.add_column("tracks", sa.Column("hq_size", sa.Integer(), nullable=True))
    # NULL — не спрашивали, 'ready' — есть, 'none' — автор не разрешил или не влез
    # в лимит Bot API. Индекс не нужен: поле читается всегда по конкретному треку.
    op.add_column("tracks", sa.Column("hq_status", sa.String(length=16), nullable=True))

    # server_default обязателен: колонка NOT NULL, а строк в users уже тысячи —
    # без значения по умолчанию ALTER TABLE не пройдёт.
    op.add_column(
        "users",
        sa.Column(
            "audio_quality",
            sa.String(length=16),
            nullable=False,
            server_default="mp3",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "audio_quality")
    op.drop_column("tracks", "hq_status")
    op.drop_column("tracks", "hq_size")
    op.drop_column("tracks", "hq_format")
    op.drop_column("tracks", "hq_file_id")
