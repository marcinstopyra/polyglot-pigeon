import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    select,
)
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError

from polyglot_pigeon.shared.db import session_scope
from polyglot_pigeon.shared.db.types import UtcDateTime

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


def test_utc_roundtrip_is_aware_and_tz_independent(
    session_factory, sample_table, local_tz
):
    # A non-UTC aware datetime, so the test also proves conversion-to-UTC.
    source = datetime(2026, 3, 15, 9, 30, 0, tzinfo=timezone(timedelta(hours=5)))

    with session_scope(session_factory) as session:
        session.execute(sample_table.insert(), {"text": "x", "created_at": source})

    with session_scope(session_factory) as session:
        loaded = session.execute(select(sample_table.c.created_at)).scalar_one()

    assert loaded.tzinfo is timezone.utc
    assert loaded == source.astimezone(timezone.utc)


def test_subsecond_precision_is_truncated(session_factory, sample_table, local_tz):
    # .999999 is the value that distinguishes truncation from MySQL's own
    # rounding, which would push this forward to 09:30:01.
    source = datetime(2026, 3, 15, 9, 30, 0, 999999, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        session.execute(sample_table.insert(), {"text": "x", "created_at": source})

    with session_scope(session_factory) as session:
        loaded = session.execute(select(sample_table.c.created_at)).scalar_one()

    assert loaded.microsecond == 0
    assert loaded == source.replace(microsecond=0)


def test_naive_datetime_raises(session_factory, sample_table, local_tz):
    naive = datetime(2026, 3, 15, 9, 30, 0)

    with pytest.raises((StatementError, OperationalError, ValueError)) as exc_info:
        with session_scope(session_factory) as session:
            session.execute(sample_table.insert(), {"text": "x", "created_at": naive})

    assert "naive" in str(exc_info.value).lower()


def test_foreign_key_violation_is_enforced(db_engine, session_factory):
    """Proves `PRAGMA foreign_keys=ON` took effect on this connection.

    SQLite ignores FK constraints by default; without the pragma this insert
    would silently succeed instead of raising.
    """
    metadata = MetaData()
    Table(
        "fk_probe_parent",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    child = Table(
        "fk_probe_child",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("parent_id", Integer, ForeignKey("fk_probe_parent.id"), nullable=False),
    )
    metadata.create_all(db_engine)

    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            session.execute(child.insert(), {"parent_id": 999})
