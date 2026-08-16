"""tracks.repair_checked_at — когда ремонт последний раз ЗАНИМАЛСЯ этим треком

🔴 Зачем (замер 16.08). Ночной `repair_catalog` выбирал кандидатов условием
«tg_file_id пуст ИЛИ трек заведён до переезда на нового бота». Второе условие не
перестаёт выполняться никогда: восстановленный трек сохраняет свой `created_at`.
Отметки «этим уже занимались» не было вообще, поэтому каждую ночь job брал одни
и те же первые 100 треков.

Что показал журнал за первую же ночь: из 100 обработанных **11 оказались живыми**
(потрачены впустую) и **17 не нашлись в источниках** (останутся не найденными и
завтра). То есть 28% бюджета ушло в повтор сразу, и доля растёт: при 17
неудачах за ночь весь бюджет в 100 треков съедается повторами примерно за
неделю, после чего ремонт каталога останавливается, продолжая рапортовать о
работе.

Колонка ставится КАЖДОМУ тронутому треку — и починенному, и живому, и
безнадёжному. Дальше выборка пропускает те, которыми занимались недавно, и
очередь наконец двигается. Безнадёжные пробуются снова через окно: источники
меняются, и «не нашлось» сегодня не значит «не найдётся никогда».

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
"""
import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("repair_checked_at", sa.DateTime(), nullable=True))
    # Частичный индекс: NULL (ещё ни разу не трогали) не индексируется, а именно
    # такие треки и составляют почти весь каталог — индекс остаётся крошечным.
    # Тот же приём, что у ix_tracks_archived (миграция e3cb5860dad1, 4 КБ).
    op.create_index(
        "ix_tracks_repair_checked",
        "tracks",
        ["repair_checked_at"],
        unique=False,
        sqlite_where=sa.text("repair_checked_at IS NOT NULL"),
        postgresql_where=sa.text("repair_checked_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tracks_repair_checked", table_name="tracks")
    op.drop_column("tracks", "repair_checked_at")
