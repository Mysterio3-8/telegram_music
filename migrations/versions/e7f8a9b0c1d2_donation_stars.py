"""donations.stars: сколько звёзд пришло в донате Telegram Stars

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-10

Хранится рядом с amount_rub, а не вместо него: прогресс цели считается в
рублях, а звёзды — это то, что реально пришло. Вместе они дают курс, по
которому засчитали, и смена STARS_RUB_RATE прошлое не переписывает.
"""
import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("donations") as batch:
        batch.add_column(sa.Column("stars", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("donations") as batch:
        batch.drop_column("stars")
