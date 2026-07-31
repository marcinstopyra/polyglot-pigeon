"""Environment-based settings shared by every process.

Every settings class in the project descends from `ServiceSettings`. There is
deliberately no module-level instance and no `get_settings()` accessor: a
process builds its settings object once in `main()` and passes it down. The
`ConfigLoader` singleton this replaced was reachable from anywhere, which is
what made a single tenant's configuration into a global.

Env variable names are spelled out as explicit `validation_alias` values rather
than derived from an `env_prefix`. Two reasons: the name in `.env.example` is
greppable back to the field that reads it, and a missing required variable
produces a `ValidationError` whose location is the variable an operator has to
set (`IMAP_PASSWORD`), not an internal field name (`password`).
"""

from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = ".env"


class Environment(str, Enum):
    """Deployment environment; controls how strict the defaults are."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class _EnvSettings(BaseSettings):
    """Common pydantic-settings behaviour.

    `populate_by_name` is deliberately **off**. With it on, pydantic-settings
    matches a field by its name as well as its alias, so `DatabaseSettings.user`
    would be populated from `USER` — the Unix username, set on every developer
    machine and in most containers — instead of `DB_USER`. Matching on the
    declared alias only is the difference between connecting as `polyglot` and
    connecting as whoever happens to be logged in.

    `extra="ignore"` matters because one `.env` file serves four services:
    `ingest` must not fail because `LLM_API_KEY` is present.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def nested(settings_cls: type[_EnvSettings]) -> Any:
    """Declare a field holding a nested settings block that reads its own vars.

    The alias is a name no environment defines. Without one, the env source
    tries to populate the composite field from a variable matching the field
    name — `user` from `USER` — and fails parsing it as JSON. The nested class
    is what reads the environment; the parent only has to stay out of the way.
    """
    return Field(
        default_factory=settings_cls,
        validation_alias=f"__nested_{settings_cls.__name__}__",
    )


class DatabaseSettings(_EnvSettings):
    """MySQL connection settings — the only reader of the `DB_*` variables.

    The variable names are load-bearing outside Python: `docker-compose.yml`
    interpolates them into the MySQL container's own environment, and
    `migrations/env.py` builds Alembic's `sqlalchemy.url` from this class.
    """

    host: str = Field(default="localhost", validation_alias="DB_HOST")
    port: int = Field(default=3306, validation_alias="DB_PORT")
    user: str = Field(default="polyglot", validation_alias="DB_USER")
    password: SecretStr = Field(
        default=SecretStr("polyglot"), validation_alias="DB_PASSWORD"
    )
    name: str = Field(default="polyglot", validation_alias="DB_NAME")
    charset: str = Field(default="utf8mb4", validation_alias="DB_CHARSET")

    @property
    def url(self) -> str:
        """SQLAlchemy URL. Credentials are percent-encoded, not interpolated raw."""
        return (
            f"mysql+pymysql://{quote_plus(self.user)}"
            f":{quote_plus(self.password.get_secret_value())}"
            f"@{self.host}:{self.port}/{self.name}?charset={self.charset}"
        )


class ServiceSettings(_EnvSettings):
    """The settings every process needs, whatever it does."""

    environment: Environment = Field(
        default=Environment.DEVELOPMENT, validation_alias="ENVIRONMENT"
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_file: Path | None = Field(default=None, validation_alias="LOG_FILE")
    database: DatabaseSettings = nested(DatabaseSettings)

    @model_validator(mode="after")
    def _require_explicit_db_password_outside_development(self) -> "ServiceSettings":
        """Refuse to run on the development database password in production.

        `DB_PASSWORD` keeps its `polyglot` default so a fresh clone works
        against `docker-compose.yml` with no `.env` at all. That default must
        not survive a production deploy, so outside development the variable has
        to be supplied explicitly — `model_fields_set` tells us whether it was,
        without this class reaching into `os.environ` behind pydantic's back.
        """
        if (
            self.environment is not Environment.DEVELOPMENT
            and "password" not in self.database.model_fields_set
        ):
            raise ValueError(
                "DB_PASSWORD must be set explicitly when ENVIRONMENT is not "
                f"'{Environment.DEVELOPMENT.value}' — refusing to fall back to "
                "the development default."
            )
        return self
