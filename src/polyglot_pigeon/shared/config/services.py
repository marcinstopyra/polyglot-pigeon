"""Per-service settings: each process declares only what it needs.

The credential blocks (`ImapSettings`, `SmtpSettings`, …) are separate from the
service classes that hold them so that composing a process out of several of
them does not mean inheriting `ServiceSettings` several times over. The
important property is negative and is asserted in the tests: `IngestSettings`
has no field that holds an LLM API key, and `ControllerSettings` has no field
that holds IMAP credentials. A service cannot leak a credential it was never
handed.

Each block sets an `env_prefix`, so `ImapSettings.password` reads
`IMAP_PASSWORD`. Nothing is spelled twice.

Credentials are `SecretStr` throughout, so a settings object that reaches a log
line renders them as `**********`.
"""

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from polyglot_pigeon.shared.config.base import ServiceSettings, _EnvSettings, nested


class ImapSettings(_EnvSettings):
    """Source mailbox the digest is built from."""

    model_config = SettingsConfigDict(env_prefix="IMAP_")

    address: str
    password: SecretStr
    server: str = "imap.gmail.com"
    port: int = 993
    fetch_days: int = 1
    mark_as_read: bool = True


class SmtpSettings(_EnvSettings):
    """Relay the digest is delivered through.

    Note what is *not* here: the recipient address. Who receives a digest is a
    property of a user, not of the relay, and it lives in `users` from PP-09.
    """

    model_config = SettingsConfigDict(env_prefix="SMTP_")

    server: str
    user: str
    password: SecretStr
    port: int = 587
    sender_name: str = "Polyglot Pigeon"
    retry_count: int = 3
    retry_delay: float = 300.0


class LlmSettings(_EnvSettings):
    """LLM provider credentials and generation parameters."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    api_key: SecretStr
    model: str
    # Base URL for OpenAI-compatible endpoints; omit for the OpenAI default.
    url: str | None = None
    # Set to "claude" to use the native Anthropic SDK.
    provider: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None


class TelegramSettings(_EnvSettings):
    """Telegram bot credentials."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

    bot_token: SecretStr


class IngestSettings(ServiceSettings):
    """`ingest`: reads the source mailbox and writes emails and chunks."""

    imap: ImapSettings = nested(ImapSettings)


class CourierSettings(ServiceSettings):
    """`courier`: sends due deliveries."""

    smtp: SmtpSettings = nested(SmtpSettings)


class ControllerSettings(ServiceSettings):
    """`controller`: runs the LLM jobs and owns the control-plane API."""

    llm: LlmSettings = nested(LlmSettings)


class BotSettings(ServiceSettings):
    """`bot`: the user-facing interaction surface.

    No prefix: `controller_base_url` already derives to `CONTROLLER_BASE_URL`.
    """

    telegram: TelegramSettings = nested(TelegramSettings)
    controller_base_url: str = "http://controller:8000"
