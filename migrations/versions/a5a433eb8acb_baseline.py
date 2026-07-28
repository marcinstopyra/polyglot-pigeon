"""baseline

Revision ID: a5a433eb8acb
Revises: 
Create Date: 2026-07-27 20:56:03.599846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import polyglot_pigeon.shared.db.types as pp


# revision identifiers, used by Alembic.
revision: str = 'a5a433eb8acb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
