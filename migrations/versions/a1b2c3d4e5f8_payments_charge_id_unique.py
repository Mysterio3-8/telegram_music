"""Уникальный charge_id в журнале выручки — ключ идемпотентности платежей.

Revision ID: a1b2c3d4e5f8
Revises: a1b2c3d4e5f7
Create Date: 2026-09-08

Почему уникальность в БД, а не только проверка в коде: ЮKassa повторяет
уведомление, пока не получит 200, и повторы могут прийти параллельно. Проверка
«есть ли такая строка» перед вставкой между двумя одновременными обработчиками
не защищает — между проверкой и вставкой влезает второй. Уникальный индекс
защищает.

Индекс ЧАСТИЧНЫЙ: у платежей Stars и старых записей charge_id может быть NULL,
а NULL-ы в уникальный индекс попадать не должны — иначе вторая строка без
charge_id была бы отбита.

Перед выпуском проверено на проде: строк в payments — 0, дублей по charge_id — 0,
то есть индекс встанет на чистых данных.
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None

_WHERE = sa.text("charge_id IS NOT NULL")


def upgrade() -> None:
    op.create_index(
        "ux_payments_charge_id",
        "payments",
        ["charge_id"],
        unique=True,
        sqlite_where=_WHERE,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index("ux_payments_charge_id", table_name="payments")
