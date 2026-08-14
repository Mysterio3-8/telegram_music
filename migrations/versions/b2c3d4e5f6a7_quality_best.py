"""audio_quality: 'original' → 'best'

Режим назывался «оригинал автора», пока замер на проде не показал, что
SoundCloud отдаёт исходный файл у 6 треков из 601 — это 1%, и ни одного у
популярных артистов. Зато 160 kbps AAC есть практически у всех, и именно он
стал содержанием платного качества. Обещание в интерфейсе пришлось привести в
соответствие с тем, что человек реально получает.

Предыдущая миграция уже уехала на прод, поэтому правка данных отдельной
ревизией, а не дописыванием в неё. Значение 'original' прожило считанные часы и
строк с ним почти наверняка нет — но если кто-то успел нажать кнопку, молча
выключать ему выбор нельзя.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET audio_quality = 'best' WHERE audio_quality = 'original'")


def downgrade() -> None:
    op.execute("UPDATE users SET audio_quality = 'original' WHERE audio_quality = 'best'")
