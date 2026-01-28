"""Pydantic models for LLM communication."""

from enum import Enum, auto

from polyglot_pigeon.models.models import MyBaseModel


class MessageRole(Enum):
    """Role of a message in a conversation."""

    SYSTEM = auto()
    USER = auto()
    ASSISTANT = auto()


class LLMMessage(MyBaseModel):
    """A message in an LLM conversation."""

    role: MessageRole
    content: str


class LLMResponse(MyBaseModel):
    """Response from an LLM completion."""

    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None
