import os
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from polyglot_pigeon.shared.config import (
    BotSettings,
    ControllerSettings,
    CourierSettings,
    DatabaseSettings,
    IngestSettings,
    SingleTenantSettings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def db_settings() -> DatabaseSettings:
    return DatabaseSettings()


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


@pytest.fixture
def alembic_config(db_settings) -> AlembicConfig:
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_settings.url)
    return cfg


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
