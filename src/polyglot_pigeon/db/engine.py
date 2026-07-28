from functools import lru_cache

from sqlalchemy import Engine, create_engine

from polyglot_pigeon.db.settings import DatabaseSettings


def create_db_engine(settings: DatabaseSettings | None = None) -> Engine:
    """Build an engine from the given (or environment-derived) settings."""
    settings = settings or DatabaseSettings.from_env()
    return create_engine(settings.url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide engine, built lazily from the environment."""
    return create_db_engine()
