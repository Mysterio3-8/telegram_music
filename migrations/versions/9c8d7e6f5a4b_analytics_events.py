"""analytics_events: единый журнал событий для аналитики

Revision ID: 9c8d7e6f5a4b
Revises: a0b1c2d3e4f5
Create Date: 2026-09-15

Владелец 15.09: собирать статистику по всему — бизнес, прослушивания, жанры,
настроения. Жанр и настроение не дублируются в событиях: отчёт берёт их из
треков, чтобы правка тегов не расходилась с историей.
"""
import sqlalchemy as sa
from alembic import op

revision = "9c8d7e6f5a4b"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=12), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("track_id", sa.Integer(), sa.ForeignKey("tracks.id"), nullable=True),
        sa.Column("props", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analytics_events_name_created", "analytics_events", ["name", "created_at"])
    op.create_index("ix_analytics_events_user_created", "analytics_events", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_analytics_events_user_created", table_name="analytics_events")
    op.drop_index("ix_analytics_events_name_created", table_name="analytics_events")
    op.drop_table("analytics_events")
