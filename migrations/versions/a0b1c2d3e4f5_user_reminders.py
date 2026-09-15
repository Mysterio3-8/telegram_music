"""user_reminders: напоминания «продлите Premium бесплатно»

Revision ID: a0b1c2d3e4f5
Revises: f8a9b0c1d2e3
Create Date: 2026-09-15

Одна строка на человека, вид напоминания и дату окончания Premium — повторный
запуск ежедневного таймера не шлёт то же сообщение второй раз.
"""
import sqlalchemy as sa
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("anchor", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_reminders_user_id", "user_reminders", ["user_id"])
    op.create_index(
        "uq_user_reminders_user_kind_anchor",
        "user_reminders",
        ["user_id", "kind", "anchor"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_user_reminders_user_kind_anchor", table_name="user_reminders")
    op.drop_index("ix_user_reminders_user_id", table_name="user_reminders")
    op.drop_table("user_reminders")
