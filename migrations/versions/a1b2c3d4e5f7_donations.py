"""donations: добровольная поддержка проекта

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-08

Отдельная таблица от payments: донат не даёт встречной услуги (дарение), и
складывать его с выручкой от Premium нельзя ни в отчёте, ни юридически.
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "donations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        # Уникальность — ключ идемпотентности: ЮKassa повторяет уведомление, пока
        # не получит 200, и без этого один платёж попал бы в рейтинг дважды.
        sa.Column("payment_id", sa.String(length=128), nullable=False),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
    )
    op.create_index("ix_donations_user_id", "donations", ["user_id"])
    op.create_index("ix_donations_rating", "donations", ["refunded_at", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_donations_rating", table_name="donations")
    op.drop_index("ix_donations_user_id", table_name="donations")
    op.drop_table("donations")
