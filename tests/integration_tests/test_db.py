import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select

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
