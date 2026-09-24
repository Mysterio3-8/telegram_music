"""Реально прослушанные секунды у события listen.

🔴 Зачем. «Часов прослушано» считалось как сумма ДЛИТЕЛЬНОСТЕЙ треков, у которых
есть событие listen. А событие ставится через 5 секунд игры — то есть человек,
пролиставший сорок треков по пять секунд, получал в профиль два часа музыки.
Владелец 22.09: «сделать нормальный подсчёт статистики… сколько часов».

Колонка nullable намеренно: у миллиона старых событий честной цифры нет и не
будет, и придумывать её нельзя. Старые события считаются по-прежнему — по
длительности трека, новые — по факту.

Revision ID: b1c2d3e4f5a7
Revises: a7b8c9d0e1f2
"""
import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a7"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("track_events", sa.Column("seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("track_events", "seconds")
