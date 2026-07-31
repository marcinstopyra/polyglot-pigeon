"""Per-service settings: each process declares only what it needs.

The credential blocks (`ImapSettings`, `SmtpSettings`, …) are separate from the
service classes that hold them so that composing a process out of several of
them does not mean inheriting `ServiceSettings` several times over. The
important property is negative and is asserted in the tests: `IngestSettings`
has no field that holds an LLM API key, and `ControllerSettings` has no field
that holds IMAP credentials. A service cannot leak a credential it was never
handed.

Credentials are `SecretStr` throughout, so a settings object that reaches a log
line renders them as `**********`.
"""

from pydantic import Field, SecretStr

from polyglot_pigeon.shared.config.base import ServiceSettings, _EnvSettings, nested


class ImapSettings(_EnvSettings):
    """Source mailbox the digest is built from."""

    address: str = Field(validation_alias="IMAP_ADDRESS")
    password: SecretStr = Field(validation_alias="IMAP_PASSWORD")
    server: str = Field(default="imap.gmail.com", validation_alias="IMAP_SERVER")
    port: int = Field(default=993, validation_alias="IMAP_PORT")
    fetch_days: int = Field(default=1, validation_alias="IMAP_FETCH_DAYS")
    mark_as_read: bool = Field(default=True, validation_alias="IMAP_MARK_AS_READ")


class SmtpSettings(_EnvSettings):
    """Relay the digest is delivered through.

    Note what is *not* here: the recipient address. Who receives a digest is a
    property of a user, not of the relay, and it lives in `users` from PP-09.
    """

    server: str = Field(validation_alias="SMTP_SERVER")
    user: str = Field(validation_alias="SMTP_USER")
    password: SecretStr = Field(validation_alias="SMTP_PASSWORD")
    port: int = Field(default=587, validation_alias="SMTP_PORT")
    sender_name: str = Field(
        default="Polyglot Pigeon", validation_alias="SMTP_SENDER_NAME"
    )
    retry_count: int = Field(default=3, validation_alias="SMTP_RETRY_COUNT")
    retry_delay: float = Field(default=300.0, validation_alias="SMTP_RETRY_DELAY")


class LlmSettings(_EnvSettings):
    """LLM provider credentials and generation parameters."""

    api_key: SecretStr = Field(validation_alias="LLM_API_KEY")
    model: str = Field(validation_alias="LLM_MODEL")
    # Base URL for OpenAI-compatible endpoints; omit for the OpenAI default.
    url: str | None = Field(default=None, validation_alias="LLM_URL")
    # Set to "claude" to use the native Anthropic SDK.
    provider: str | None = Field(default=None, validation_alias="LLM_PROVIDER")
    max_tokens: int = Field(default=4096, validation_alias="LLM_MAX_TOKENS")
    temperature: float = Field(default=0.7, validation_alias="LLM_TEMPERATURE")
    input_cost_per_million: float | None = Field(
        default=None, validation_alias="LLM_INPUT_COST_PER_MILLION"
    )
    output_cost_per_million: float | None = Field(
        default=None, validation_alias="LLM_OUTPUT_COST_PER_MILLION"
    )


class TelegramSettings(_EnvSettings):
    """Telegram bot credentials."""

    bot_token: SecretStr = Field(validation_alias="TELEGRAM_BOT_TOKEN")


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
    """`bot`: the user-facing interaction surface."""

    telegram: TelegramSettings = nested(TelegramSettings)
    controller_base_url: str = Field(
        default="http://controller:8000", validation_alias="CONTROLLER_BASE_URL"
    )
