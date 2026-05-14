"""add is_admin column to userinfo

Revision ID: a4b6c8d0e1f2
Revises: d8b3a1c2f4e5
Create Date: 2026-05-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4b6c8d0e1f2"
down_revision: Union[str, Sequence[str], None] = "d8b3a1c2f4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "userinfo",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("userinfo", "is_admin")
