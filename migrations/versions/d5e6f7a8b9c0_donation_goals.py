"""Цели сбора: donation_goals + привязка донатов к цели

Revision ID: d5e6f7a8b9c0
Revises: a1b2c3d4e5f8
Create Date: 2026-09-09

Прогресс цели намеренно НЕ хранится числом — он всегда считается суммой
донатов с этим goal_id. Хранимый счётчик стал бы второй правдой о деньгах и
разошёлся бы с первой на первом же возврате или повторе уведомления кассы.
"""
import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "donation_goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("target_rub", sa.Integer(), nullable=False),
        sa.Column("image_file_id", sa.String(length=256), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("channel_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("channel_message_id", sa.BigInteger(), nullable=True),
        # True у активной, NULL у закрытой. Уникальность по этой колонке и есть
        # правило «активная цель одна»: NULL-ы в уникальном индексе считаются
        # разными, поэтому закрытых целей может быть сколько угодно.
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("reached_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("is_active", name="uq_donation_goals_active"),
    )

    # ⚠️ batch_alter_table обязателен: SQLite не умеет ALTER TABLE ADD CONSTRAINT,
    # и внешний ключ на donation_goals иначе просто не создастся. Alembic под
    # капотом пересоздаёт таблицу и переносит данные.
    with op.batch_alter_table("donations") as batch:
        batch.add_column(
            sa.Column("provider", sa.String(length=16), server_default="yookassa", nullable=False)
        )
        batch.add_column(sa.Column("ton_nano", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("rub_per_ton", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("goal_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("is_anonymous", sa.Boolean(), server_default="0", nullable=False)
        )
        batch.create_foreign_key(
            "fk_donations_goal", "donation_goals", ["goal_id"], ["id"]
        )
        batch.create_index("ix_donations_goal", ["goal_id", "refunded_at"])


def downgrade() -> None:
    with op.batch_alter_table("donations") as batch:
        batch.drop_index("ix_donations_goal")
        batch.drop_constraint("fk_donations_goal", type_="foreignkey")
        batch.drop_column("is_anonymous")
        batch.drop_column("goal_id")
        batch.drop_column("rub_per_ton")
        batch.drop_column("ton_nano")
        batch.drop_column("provider")
    op.drop_table("donation_goals")
