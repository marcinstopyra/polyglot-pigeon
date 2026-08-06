from sqlalchemy import Engine, create_engine

from polyglot_pigeon.shared.config import DatabaseSettings


def create_db_engine(settings: DatabaseSettings) -> Engine:
    """Build an engine from the given settings.

    Settings are a required argument rather than an optional one defaulting to
    the environment: a process constructs them once in `main()` and passes them
    down. The previous `get_engine()` — an `lru_cache`d factory that read the
    environment on first call — was the same process-wide global that
    `ConfigLoader` was, and PP-04 removes both.
    """
    return create_engine(settings.url, pool_pre_ping=True, future=True)
