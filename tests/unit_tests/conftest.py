import os
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from polyglot_pigeon.shared.config import (
    BotSettings,
    ControllerSettings,
    CourierSettings,
    IngestSettings,
    SingleTenantSettings,
)
from polyglot_pigeon.shared.db import Base, get_session_factory

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_engine():
    """A fresh in-memory SQLite database, isolated per test (PP-28).

    Nothing here needs MySQL: what these tests exercise is dialect-neutral
    Python (bind/result processors, ORM mapping, query logic). `StaticPool`
    keeps a single connection alive for the engine's lifetime so schema
    created via `metadata.create_all` is visible to the test body — plain
    `sqlite://` hands out a brand-new, empty database per connection.
    Function-scoped, unlike the old MySQL fixture: spinning up in-memory
    SQLite is free, so there is no reason to let tests share rows.

    Schema comes from `Base.metadata.create_all` — the ORM models directly,
    not Alembic. Alembic owns schema creation in production and is what
    `tests/integration_tests/test_migrations.py` verifies (including that its
    output matches `Base.metadata`); the unit suite doesn't need a second,
    slower way to prove the same migration scripts work.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _):
        # SQLite ignores FK constraints unless told otherwise per connection.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine) -> sessionmaker[Session]:
    """The same factory `services/*` will build via `get_session_factory` in
    production, bound to the SQLite `db_engine` instead of a real MySQL one.

    Tests should reach for this (with `session_scope`, imported from
    `polyglot_pigeon.shared.db`) rather than `db_engine.begin()`/`.connect()`
    directly, so the suite exercises the actual session lifecycle the app
    uses rather than bypassing it.
    """
    return get_session_factory(db_engine)


def env_aliases(settings_cls: type[BaseSettings]) -> set[str]:
    """Every environment variable a settings class (and its nested ones) reads.

    Derived from the model the same way pydantic-settings derives it — the
    class's `env_prefix` plus the field name — rather than hard-coded, so a new
    field cannot leak the developer's own environment into a test by being
    forgotten here. `test_settings.py` uses this to assert `.env.example` is
    complete.
    """
    prefix = str(settings_cls.model_config.get("env_prefix", "")).upper()
    names: set[str] = set()
    for field_name, field in settings_cls.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseSettings):
            # A nested block reads its own variables under its own prefix; the
            # parent's placeholder alias for it is not a real variable.
            names |= env_aliases(annotation)
        else:
            names.add(prefix + field_name.upper())
    return names


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Isolate settings construction from the developer's own environment.

    pydantic-settings reads two sources, and both have to go or a test asserting
    "IMAP_PASSWORD is required" passes or fails depending on whose machine it
    ran on:

    - Environment variables, cleared below.
    - The `.env` file, resolved relative to the working directory — so the
      working directory becomes an empty one. Passing `_env_file=None` to the
      settings class is not enough: `nested()` builds each sub-settings object
      through `default_factory`, which takes no such argument, so `ImapSettings`
      would still find the real file.
    """
    monkeypatch.chdir(tmp_path)
    for settings_cls in (
        BotSettings,
        ControllerSettings,
        CourierSettings,
        IngestSettings,
        SingleTenantSettings,
    ):
        for name in env_aliases(settings_cls):
            monkeypatch.delenv(name, raising=False)
    for name in list(os.environ):
        if name.startswith(("DB_", "IMAP_", "SMTP_", "LLM_", "USER_", "PIPELINE_")):
            monkeypatch.delenv(name, raising=False)
    return monkeypatch
