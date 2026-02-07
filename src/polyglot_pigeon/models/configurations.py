from enum import Enum, auto
from pathlib import Path
from typing import Optional

from pydantic import Field

from polyglot_pigeon.models.models import MyBaseModel


class LLMProvider(Enum):
    CLAUDE = auto()
    PERPLEXITY = auto()
    OPENAI = auto()


class SourceEmailConfig(MyBaseModel):
    address: str
    app_password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    fetch_days: int = 1
    mark_as_read: bool = True


class LLMConfig(MyBaseModel):
    provider: LLMProvider
    api_key: str
    model: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7


class Language(Enum):
    ENGLISH = auto()
    GERMAN = auto()
    RUSSIAN = auto()


class LanguageLevel(Enum):
    A1 = auto()
    A2 = auto()
    B1 = auto()
    B2 = auto()
    C1 = auto()
    C2 = auto()


class LanguageConfig(MyBaseModel):
    target: Language
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
    file: Path = Path("logs/polyglot_pigeon.log")


class Config(MyBaseModel):
    source_email: SourceEmailConfig
    llm: LLMConfig
    language: LanguageConfig
    target_email: TargetEmailConfig
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
