from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from polyglot_pigeon.db.engine import get_engine


def get_session_factory(engine=None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine or get_engine(), expire_on_commit=False, future=True
    )


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """Provide a transactional session: commits on success, rolls back on error."""
    factory = session_factory or get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
