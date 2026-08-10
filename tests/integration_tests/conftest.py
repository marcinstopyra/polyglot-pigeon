from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from polyglot_pigeon.shared.config import DatabaseSettings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def db_settings() -> DatabaseSettings:
    return DatabaseSettings()


@pytest.fixture(scope="session")
def db_engine(db_settings):
    """The real MySQL engine.

    This suite exists precisely to test what the unit suite (PP-28, SQLite)
    cannot: MySQL-specific behaviour like charset handling, native `ENUM`
    ordering, and Alembic migrations against the real dialect. Unlike the unit
    suite, this one is not meant to run everywhere — but when it does run, an
    unreachable database is a failure, not an ambient skip: a skip here would
    recreate the exact silent-opt-out bug PP-28 was written to eliminate.
    Opting out is `pytest -m "not mysql"`, a deliberate choice, never this
    fixture's default.
    """
    engine = create_engine(db_settings.url, pool_pre_ping=True, future=True)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        raise RuntimeError(
            f"MySQL not reachable at {db_settings.host}:{db_settings.port}. "
            "The integration suite requires a running database — see "
            "`make test-integration` / `make db-up` — or run "
            '`pytest -m "not mysql"` to opt out explicitly.'
        ) from exc
    yield engine
    engine.dispose()


@pytest.fixture
def alembic_config(db_settings) -> AlembicConfig:
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_settings.url)
    return cfg
