"""empty message

Revision ID: e82877344456
Revises: 1199984eda18
Create Date: 2026-04-24 23:01:08.514413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e82877344456'
down_revision: Union[str, Sequence[str], None] = '1199984eda18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
