"""funnel_events: первое прохождение шагов воронки новичка

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-15

Замер 15.09: из подписавшихся на канал 46% не делают в боте ничего, и куда они
нажимают, не видно. Таблица маленькая: одна строка на пользователя и шаг.
"""
import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funnel_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("step", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_funnel_events_user_id", "funnel_events", ["user_id"])
    op.create_index("ix_funnel_events_step_user", "funnel_events", ["step", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_funnel_events_step_user", table_name="funnel_events")
    op.drop_index("ix_funnel_events_user_id", table_name="funnel_events")
    op.drop_table("funnel_events")
