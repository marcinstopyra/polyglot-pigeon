import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from polyglot_pigeon.shared.db.settings import DatabaseSettings


@pytest.fixture(scope="session")
def db_settings() -> DatabaseSettings:
    return DatabaseSettings.from_env()


@pytest.fixture(scope="session")
def db_engine(db_settings):
    engine = create_engine(db_settings.url, pool_pre_ping=True, future=True)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(
            f"MySQL not reachable at {db_settings.host}:{db_settings.port}: {exc}"
        )
    yield engine
    engine.dispose()
