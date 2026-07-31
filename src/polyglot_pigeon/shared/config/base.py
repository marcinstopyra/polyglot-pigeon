"""Environment-based settings shared by every process.

Every settings class in the project descends from `ServiceSettings`. There is
deliberately no module-level instance and no `get_settings()` accessor: a
process builds its settings object once in `main()` and passes it down. The
`ConfigLoader` singleton this replaced was reachable from anywhere, which is
what made a single tenant's configuration into a global.

Env variable names are derived from the field name and the class's `env_prefix`:
`DatabaseSettings.user` reads `DB_USER`. The mapping is mechanical, so the
prefix on the class is the only thing to keep in step with `.env.example` — and
a test asserts the two agree, so a new field cannot land undocumented.

What a prefix does not give you is a good failure. pydantic reports a missing
field by its field name (`password`), which is not what an operator sets. The
`MissingSettingsError` hook below restores that, reporting `IMAP_PASSWORD`.
"""

from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = ".env"


class MissingSettingsError(RuntimeError):
    """A required environment variable was not set.

    Raised in place of pydantic's `ValidationError` for missing values only, so
    that the message names variables rather than fields. Every other validation
    failure — a non-numeric port, an unknown language — still surfaces as a
    `ValidationError` with pydantic's own diagnostics.
    """


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

    def __init__(self, **kwargs: Any) -> None:
        """Report missing variables by the name an operator has to set.

        pydantic locates a missing field by its field name, so an unset
        `IMAP_PASSWORD` is reported as `password` — accurate inside the model,
        useless in a deployment. Rebuilding the name from the prefix turns the
        failure into an instruction.

        A nested block raises this from inside its own `default_factory`, which
        propagates through the parent untouched, so the message names the block
        that actually failed.
        """
        try:
            super().__init__(**kwargs)
        except ValidationError as exc:
            prefix = str(self.model_config.get("env_prefix", "")).upper()
            missing = [
                prefix + "_".join(str(part) for part in error["loc"]).upper()
                for error in exc.errors()
                if error["type"] == "missing"
            ]
            if missing:
                raise MissingSettingsError(
                    f"{type(self).__name__}: missing required environment "
                    f"variable(s): {', '.join(missing)}"
                ) from None
            raise


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

    # Merged with `_EnvSettings.model_config`, not replacing it: pydantic
    # combines `model_config` across the MRO, so `env_file` and `extra` carry.
    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = "localhost"
    port: int = 3306
    user: str = "polyglot"
    password: SecretStr = SecretStr("polyglot")
    name: str = "polyglot"
    charset: str = "utf8mb4"

    @property
    def url(self) -> str:
        """SQLAlchemy URL. Credentials are percent-encoded, not interpolated raw."""
        return (
            f"mysql+pymysql://{quote_plus(self.user)}"
            f":{quote_plus(self.password.get_secret_value())}"
            f"@{self.host}:{self.port}/{self.name}?charset={self.charset}"
        )


class ServiceSettings(_EnvSettings):
    """The settings every process needs, whatever it does.

    No `env_prefix`: these three already derive to the names they should have —
    `ENVIRONMENT`, `LOG_LEVEL`, `LOG_FILE`.
    """

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_file: Path | None = None
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
