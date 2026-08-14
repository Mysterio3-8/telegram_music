"""users.cover_as_file — присылать обложку отдельной картинкой

Вторая половина пункта 3 спеки 13.08 (первая — выбор качества — уехала вместе с
пунктом 1). Обложка и сейчас вшита в аудиофайл и видна в плеере; опция нужна
тем, кто складывает музыку в свою медиатеку и хочет картинку отдельным файлом.

По умолчанию выключено: лишнее сообщение на каждый трек засоряет переписку у
тех, кто просто слушает.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("cover_as_file", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "cover_as_file")
