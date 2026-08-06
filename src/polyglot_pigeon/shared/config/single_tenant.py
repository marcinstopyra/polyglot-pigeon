"""Settings for the single-tenant monolith, and the bridge to today's `Config`.

**This module is temporary.** Everything under `SingleTenantUserSettings` is a
property of a *user*, not of a process, and belongs in the `users` and
`subscriptions` rows introduced by PP-09. Until those rows exist there is
nowhere else to put them, and PP-04 is explicit that the seeded development user
is the stand-in in the meantime (PP-26 decides whether the existing
`config.yaml` deployments are seeded or re-onboarded).

Keeping the stand-in here, in one class named after the thing it is standing in
for, is the point: when PP-09 lands, deleting this module and its `.env`
variables is the whole migration. The alternative — leaving these five fields
scattered across `ingest` and `courier` settings — would bury per-user state
inside process configuration exactly where the `ConfigLoader` singleton had it.

`to_config()` assembles the legacy `Config` model the existing pipeline still
takes, so the monolith keeps running unchanged while the settings mechanism
underneath it changes.
"""

import re
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from polyglot_pigeon.shared.config.base import ServiceSettings, _EnvSettings, nested
from polyglot_pigeon.shared.config.services import (
    ImapSettings,
    LlmSettings,
    SmtpSettings,
)
from polyglot_pigeon.shared.models.configurations import (
    Config,
    LanguageConfig,
    LanguageLevel,
    LLMConfig,
    LoggingConfig,
    PipelineConfig,
    ScheduleConfig,
    SourceEmailConfig,
    TargetEmailConfig,
)

E = TypeVar("E", bound=Enum)

# ISO 639-1, optionally with a region suffix ("es", "pt-br"). A format check
# only — whether the code names a language this deployment actually supports
# is enforced by the `languages` table (PP-05), which this object has no
# session to query: `SingleTenantUserSettings` is built once at startup,
# before any database connection exists.
_LANGUAGE_CODE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")


def parse_enum_by_name(value: Any, enum_type: type[E]) -> Any:
    """Resolve a string to an enum member by name, case-insensitively.

    `config.yaml` spelled these `english` / `b1`, and `MyBaseModel` accepted
    that. Environment variables are the same kind of hand-written input, so they
    accept the same spellings. Anything unrecognised is passed through for
    pydantic to reject, which lists the valid members in the error.
    """
    if isinstance(value, str):
        by_name = {member.name.lower(): member for member in enum_type}
        return by_name.get(value.strip().lower(), value)
    return value


class SingleTenantUserSettings(_EnvSettings):
    """The one user's preferences. Becomes `users` + `subscriptions` in PP-09."""

    model_config = SettingsConfigDict(env_prefix="USER_")

    target_email: str
    known_language: str
    target_language: str
    language_level: LanguageLevel
    timezone: str = "UTC"
    send_time: str = "12:00"
    schedule_enabled: bool = True

    @field_validator("known_language", "target_language", mode="after")
    @classmethod
    def _validate_language_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _LANGUAGE_CODE.fullmatch(normalized):
            raise ValueError(
                f"{value!r} is not a valid language code — expected an "
                'ISO 639-1 code, optionally with a region suffix ("es", "pt-br")'
            )
        return normalized

    @field_validator("language_level", mode="before")
    @classmethod
    def _parse_level(cls, value: Any) -> Any:
        return parse_enum_by_name(value, LanguageLevel)


class PipelineSettings(_EnvSettings):
    """Digest-shaping knobs that are neither credentials nor user preferences."""

    model_config = SettingsConfigDict(env_prefix="PIPELINE_")

    # Shorter than the legacy `PipelineConfig.max_articles_in_final_email` it
    # feeds, so the variable stays `PIPELINE_MAX_ARTICLES` without an alias.
    max_articles: int = 7
    min_chunk_chars: int = 80
    max_chunks_per_email: int = 60
    show_cost_in_footer: bool = True
    prompts_path: Path = Path("/app/prompts.yaml")


class SingleTenantSettings(ServiceSettings):
    """Every setting the current monolith needs, in one object built at startup.

    Once the services are split (PP-20…PP-23) each of them constructs its own
    narrow settings class instead; this one exists because a single process is
    still doing all four jobs.
    """

    imap: ImapSettings = nested(ImapSettings)
    smtp: SmtpSettings = nested(SmtpSettings)
    llm: LlmSettings = nested(LlmSettings)
    user: SingleTenantUserSettings = nested(SingleTenantUserSettings)
    pipeline: PipelineSettings = nested(PipelineSettings)

    def to_config(self) -> Config:
        """Build the legacy `Config` the scheduler and pipeline still consume.

        This is the only place secrets are unwrapped out of `SecretStr`, and it
        happens on the way into objects that are handed straight to the IMAP,
        SMTP and LLM clients.
        """
        return Config(
            source_email=SourceEmailConfig(
                address=self.imap.address,
                app_password=self.imap.password.get_secret_value(),
                imap_server=self.imap.server,
                imap_port=self.imap.port,
                fetch_days=self.imap.fetch_days,
                mark_as_read=self.imap.mark_as_read,
            ),
            llm=LLMConfig(
                api_key=self.llm.api_key.get_secret_value(),
                model=self.llm.model,
                url=self.llm.url,
                provider=self.llm.provider,
                max_tokens=self.llm.max_tokens,
                temperature=self.llm.temperature,
                input_cost_per_million=self.llm.input_cost_per_million,
                output_cost_per_million=self.llm.output_cost_per_million,
            ),
            language=LanguageConfig(
                known=self.user.known_language,
                target=self.user.target_language,
                level=self.user.language_level,
            ),
            target_email=TargetEmailConfig(
                address=self.user.target_email,
                smtp_server=self.smtp.server,
                smtp_port=self.smtp.port,
                smtp_user=self.smtp.user,
                smtp_password=self.smtp.password.get_secret_value(),
                sender_name=self.smtp.sender_name,
                retry_count=self.smtp.retry_count,
                retry_delay=self.smtp.retry_delay,
            ),
            schedule=ScheduleConfig(
                time=self.user.send_time,
                timezone=self.user.timezone,
                enabled=self.user.schedule_enabled,
            ),
            logging=LoggingConfig(level=self.log_level, file=self.log_file),
            pipeline=PipelineConfig(
                max_articles_in_final_email=self.pipeline.max_articles,
                min_chunk_chars=self.pipeline.min_chunk_chars,
                max_chunks_per_email=self.pipeline.max_chunks_per_email,
                show_cost_in_footer=self.pipeline.show_cost_in_footer,
                prompts_path=self.pipeline.prompts_path,
            ),
        )
