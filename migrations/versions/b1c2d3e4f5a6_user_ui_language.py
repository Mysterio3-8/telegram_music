"""user ui_language

Осознанный выбор языка интерфейса. Отдельно от users.language, который приезжает
из профиля Telegram и перезаписывается на каждом /start.

Revision ID: b1c2d3e4f5a6
Revises: e3cb5860dad1
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "e3cb5860dad1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ui_language", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ui_language")
