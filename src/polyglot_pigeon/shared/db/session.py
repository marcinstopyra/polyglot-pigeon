from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to an explicitly supplied engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a transactional session: commits on success, rolls back on error."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
