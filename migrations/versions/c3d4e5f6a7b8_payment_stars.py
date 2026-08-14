"""payments.amount_stars — выручка в Telegram Stars отдельной колонкой

Stars вернулись в интерфейс (пункт 2 спеки 13.08): официальная партнёрская
программа Telegram работает только с ними, со сторонним эквайрингом её включить
нельзя. До этой миграции звёздный платёж писался с `amount_rub=0`, то есть в
отчёте выглядел как бесплатная подписка — сумма терялась целиком.

Складывать звёзды с рублями в одну колонку нельзя: курс плавающий, Telegram
удерживает свою долю, и число «рубли плюс звёзды» не означало бы ничего.
Поэтому две колонки и две строки в админ-отчёте.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("amount_stars", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("payments", "amount_stars")
