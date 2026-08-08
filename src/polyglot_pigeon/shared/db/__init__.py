from polyglot_pigeon.shared.db.base import TABLE_ARGS, Base
from polyglot_pigeon.shared.db.engine import create_db_engine

# Imported for its side effect of registering `Language` on `Base.metadata` —
# unused directly here, but re-exported so callers don't reach into the
# submodule, and so `migrations/env.py`'s `from ...db.base import Base` (which
# runs this package's `__init__` first) sees every mapped class.
from polyglot_pigeon.shared.db.models import Language
from polyglot_pigeon.shared.db.session import get_session_factory, session_scope
from polyglot_pigeon.shared.db.types import UtcDateTime

__all__ = [
    "TABLE_ARGS",
    "Base",
    "Language",
    "UtcDateTime",
    "create_db_engine",
    "get_session_factory",
    "session_scope",
]
