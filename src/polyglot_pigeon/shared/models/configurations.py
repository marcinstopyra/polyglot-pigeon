from enum import Enum, auto
from pathlib import Path

from pydantic import Field

from polyglot_pigeon.shared.models.models import MyBaseModel


class SourceEmailConfig(MyBaseModel):
    address: str
    app_password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    fetch_days: int = 1
    mark_as_read: bool = True


class LLMConfig(MyBaseModel):
    api_key: str
    model: str
    url: str | None = (
        None  # base_url for OpenAI-compatible endpoints; omit for OpenAI default
    )
    provider: str | None = None  # set to "claude" to use the native Anthropic SDK
    max_tokens: int = 4096
    temperature: float = 0.7
    input_cost_per_million: float | None = None  # USD per 1M input tokens
    output_cost_per_million: float | None = None  # USD per 1M output tokens


class LanguageLevel(Enum):
    A1 = auto()
    A2 = auto()
    B1 = auto()
    B2 = auto()
    C1 = auto()
    C2 = auto()


class Channel(Enum):
    """Delivery channel. Adding one means writing a delivery implementation,
    so unlike `language` it can never be data-only (architecture doc §6)."""

    EMAIL = auto()
    TELEGRAM = auto()


# The old `Language` enum's members, by the `languages.code` row that
# replaces each one (PP-05 — see `migrations/versions/4d3179cd3311_*`, the
# source of truth this duplicates). `LanguageConfig.known` / `.target` are now
# plain codes, but the legacy single-tenant `pipeline.py` still needs a
# display name for its LLM prompts and has no database session to look one up
# with — `SingleTenantSettings` is built once at startup, before any query
# runs. Delete this alongside `single_tenant.py` when PP-09 lands and the
# pipeline reads `languages` for real.
LANGUAGE_DISPLAY_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "ru": "Russian",
    "it": "Italian",
    "es": "Spanish",
    "tr": "Turkish",
    "pl": "Polish",
}


class LanguageConfig(MyBaseModel):
    known: str
    target: str
    level: LanguageLevel


class TargetEmailConfig(MyBaseModel):
    address: str
    smtp_server: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    sender_name: str = "Polyglot Pigeon"
    retry_count: int = Field(
        default=3, description="Number of retry attempts on network timeout"
    )
    retry_delay: float = Field(
        default=300.0, description="Delay between retry attempts in seconds"
    )


class ScheduleConfig(MyBaseModel):
    time: str = "12:00"
    timezone: str = "UTC"
    enabled: bool = True


class LoggingConfig(MyBaseModel):
    level: str = "INFO"
    # None logs to the console only, which is the right default for a container.
    # Set LOG_FILE to also write to disk.
    file: Path | None = None


class PipelineConfig(MyBaseModel):
    max_articles_in_final_email: int = 7
    min_chunk_chars: int = 80
    max_chunks_per_email: int = 60
    show_cost_in_footer: bool = True
    prompts_path: Path = Path("/app/prompts.yaml")


class Config(MyBaseModel):
    source_email: SourceEmailConfig
    llm: LLMConfig
    language: LanguageConfig
    target_email: TargetEmailConfig
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
