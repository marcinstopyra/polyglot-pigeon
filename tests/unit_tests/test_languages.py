"""Tests for the `Language` enum retirement (PP-05).

`languages`-table tests that need the real, migrated schema and seed data
live in `tests/integration_tests/test_languages.py` instead (PP-28) — Alembic
can't run against in-memory SQLite (see that file's docstring)."""

import re

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from polyglot_pigeon.shared.db import session_scope
from polyglot_pigeon.shared.models.configurations import LanguageLevel
from tests.unit_tests.conftest import REPO_ROOT


def test_language_enum_member_access_is_gone_from_src():
    """The old `Language` enum must not exist — see the PP-05 acceptance
    criteria: `rg "Language\\." src/` should find no enum member access.

    `Language\\.` (a literal dot right after the word) only matches attribute
    access like `Language.ENGLISH`, not the unrelated `LanguageLevel` /
    `LanguageConfig` identifiers, nor the new `Language` ORM row class, which
    is never accessed that way.
    """
    pattern = re.compile(r"\bLanguage\.")
    hits: list[str] = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")

    assert hits == []


class TestLanguageLevelOrdering:
    """`level` stays a Python enum (`LanguageLevel`), mapped to a native MySQL
    `ENUM` — which sorts by declaration order, not alphabetically. This is
    what an `ORDER BY` on a real `level` column depends on."""

    _metadata = sa.MetaData()
    _probe = sa.Table(
        "language_level_order_probe",
        _metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("level", sa.Enum(LanguageLevel), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    @pytest.fixture
    def probe_table(self, db_engine):
        self._metadata.create_all(db_engine)
        yield self._probe
        self._metadata.drop_all(db_engine)

    def test_order_by_level_returns_cefr_order(self, session_factory, probe_table):
        shuffled = [
            LanguageLevel.C1,
            LanguageLevel.A1,
            LanguageLevel.B2,
            LanguageLevel.C2,
            LanguageLevel.A2,
            LanguageLevel.B1,
        ]
        with session_scope(session_factory) as session:
            session.execute(
                probe_table.insert(),
                [{"level": level} for level in shuffled],
            )

        with session_scope(session_factory) as session:
            ordered = (
                session.execute(
                    select(probe_table.c.level).order_by(probe_table.c.level)
                )
                .scalars()
                .all()
            )

        assert ordered == [
            LanguageLevel.A1,
            LanguageLevel.A2,
            LanguageLevel.B1,
            LanguageLevel.B2,
            LanguageLevel.C1,
            LanguageLevel.C2,
        ]
