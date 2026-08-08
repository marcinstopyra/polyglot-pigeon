"""languages table

Revision ID: 4d3179cd3311
Revises: a5a433eb8acb
Create Date: 2026-08-06 20:37:40.162191

PP-05: introduces `languages` as reference data — writable only through
migrations like this one (architecture doc §5). The seed rows below are a
literal snapshot of the languages the product supports today, not a live
reference to Python code: a migration is a historical record, and importing
an application constant here would let a later edit to that constant silently
rewrite what this migration seeds when replayed from scratch.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import polyglot_pigeon.shared.db.types as pp


# revision identifiers, used by Alembic.
revision: str = '4d3179cd3311'
down_revision: Union[str, Sequence[str], None] = 'a5a433eb8acb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

languages_table = sa.table(
    "languages",
    sa.column("code", sa.String),
    sa.column("name_en", sa.String),
    sa.column("name_native", sa.String),
)

# code, name_en, name_native — the languages the current single-tenant
# monolith already supports (was the `Language` enum this table replaces).
SEED_LANGUAGES = [
    ("en", "English", "English"),
    ("de", "German", "Deutsch"),
    ("ru", "Russian", "Русский"),
    ("it", "Italian", "Italiano"),
    ("es", "Spanish", "Español"),
    ("tr", "Turkish", "Türkçe"),
    ("pl", "Polish", "Polski"),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "languages",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name_en", sa.String(length=64), nullable=False),
        sa.Column("name_native", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_languages")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.bulk_insert(
        languages_table,
        [
            {"code": code, "name_en": name_en, "name_native": name_native}
            for code, name_en, name_native in SEED_LANGUAGES
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("languages")
