import time
from datetime import datetime, timezone

import pytest
from alembic import command
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import DataError, OperationalError

from polyglot_pigeon.shared.db.types import UtcDateTime

pytestmark = pytest.mark.mysql

_metadata = MetaData()
_sample = Table(
    "db_foundation_sample",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("text", String(255), nullable=False),
    Column("created_at", UtcDateTime, nullable=False),
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)


@pytest.fixture
def sample_table(db_engine):
    _metadata.create_all(db_engine)
    yield _sample
    _metadata.drop_all(db_engine)


@pytest.fixture(params=["UTC", "America/New_York"])
def local_tz(request, monkeypatch):
    """Run the marked test under both a UTC and a non-UTC process TZ.

    A UTC-only run can pass while the code silently relies on local time —
    see PP-02's acceptance criteria.
    """
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    time.tzset()


def test_db_reachable(db_engine):
    with db_engine.connect() as conn:
        assert conn.execute(select(1)).scalar_one() == 1


def test_utf8mb4_roundtrip(db_engine, sample_table, local_tz):
    text = "café ☕️ – naïve résumé 日本語"
    with db_engine.begin() as conn:
        conn.execute(
            sample_table.insert(),
            {"text": text, "created_at": datetime.now(timezone.utc)},
        )

    with db_engine.connect() as conn:
        row = conn.execute(select(sample_table.c.text)).scalar_one()
    assert row == text


def test_utf8mb4_roundtrip_fails_under_utf8mb3(db_settings, sample_table):
    """Proves `test_utf8mb4_roundtrip` exercises the full charset chain —
    server, database, table *and* connection — rather than just the driver:
    the same write fails once the connection charset is downgraded.

    The character matters: most emoji with a visible glyph (e.g. "☕️", a BMP
    symbol plus a variation selector) encode in 3 bytes and fit in utf8mb3
    just fine. Only a genuine astral-plane character like "🎉" (U+1F389)
    needs the 4th byte utf8mb4 exists for.
    """
    mb3_url = db_settings.url.replace(
        f"charset={db_settings.charset}", "charset=utf8mb3"
    )
    engine = create_engine(mb3_url, future=True)
    try:
        with pytest.raises((DataError, OperationalError)):
            with engine.begin() as conn:
                conn.execute(
                    sample_table.insert(),
                    {"text": "🎉", "created_at": datetime.now(timezone.utc)},
                )
    finally:
        engine.dispose()


def test_varchar_length_is_enforced(db_engine, sample_table):
    """SQLite silently accepts an over-length write; only a real MySQL, under
    the strict SQL mode it defaults to, rejects it — so this can never be a
    unit test."""
    too_long = "x" * 256  # sample_table.text is VARCHAR(255)
    with pytest.raises(DataError):
        with db_engine.begin() as conn:
            conn.execute(
                sample_table.insert(),
                {"text": too_long, "created_at": datetime.now(timezone.utc)},
            )


def test_utcdatetime_roundtrip_independent_of_session_timezone(db_engine, sample_table):
    """`UtcDateTime` stores plain `DATETIME`, which MySQL never converts for
    session `time_zone` (unlike `TIMESTAMP`) — the round trip must hold even
    when the session isn't UTC. `microsecond=0`: the type truncates to second
    precision by design, which isn't what this test is checking."""
    moment = datetime(2026, 3, 14, 15, 9, 26, tzinfo=timezone.utc)
    with db_engine.begin() as conn:
        conn.execute(text("SET time_zone = '+05:00'"))
        conn.execute(
            sample_table.insert(),
            {"text": "tz-independence", "created_at": moment},
        )
        stored = conn.execute(
            select(sample_table.c.created_at).where(
                sample_table.c.text == "tz-independence"
            )
        ).scalar_one()
    assert stored == moment


def test_table_names_are_lowercase(db_engine, alembic_config):
    """`lower_case_table_names` differs between a Linux server and a macOS
    laptop (architecture doc §6); staying lowercase everywhere sidesteps the
    divergence rather than relying on MySQL to normalize case consistently."""
    command.upgrade(alembic_config, "head")
    try:
        table_names = inspect(db_engine).get_table_names()
        assert table_names
        assert all(name == name.lower() for name in table_names)
    finally:
        command.downgrade(alembic_config, "base")
