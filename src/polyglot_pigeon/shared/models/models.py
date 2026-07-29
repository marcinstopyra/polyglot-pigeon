from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_serializer, model_validator


class MyBaseModel(BaseModel):
    """Base model that automatically parses string values to Enums and serializes special types."""

    @model_validator(mode="before")
    @classmethod
    def parse_enums(cls, data: Any) -> Any:
        """Convert string values to Enum types for all Enum fields (case-insensitive)."""
        if not isinstance(data, dict):
            return data

        # Get all field annotations
        annotations = cls.model_fields

        # Process each field
        parsed_data = data.copy()
        for field_name, field_info in annotations.items():
            if field_name not in parsed_data:
                continue

            field_type = field_info.annotation
            field_value = parsed_data[field_name]

            # Check if the field type is an Enum
            if isinstance(field_type, type) and issubclass(field_type, Enum):
                if isinstance(field_value, str):
                    # Create a case-insensitive lookup dict
                    enum_lookup = {member.name.lower(): member for member in field_type}

                    # Try to find the enum value (case-insensitive)
                    normalized_value = field_value.lower()
                    if normalized_value in enum_lookup:
                        parsed_data[field_name] = enum_lookup[normalized_value]
                    # If not found, let Pydantic handle the validation error

        return parsed_data

    @model_serializer(mode="wrap", when_used="always")
    def serialize_special_types(self, serializer: Any, info: Any) -> dict[str, Any]:
        """Convert Path objects to strings and Enums to their lowercase string names."""
        # Get the default serialization
        data = serializer(self)

        # Process all values in the serialized data
        return self._convert_values(data)

    @classmethod
    def _convert_values(cls, obj: Any) -> Any:
        """Recursively convert Path and Enum objects to lowercase strings."""
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, Enum):
            return obj.name.lower()
        elif isinstance(obj, dict):
            return {key: cls._convert_values(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return type(obj)(cls._convert_values(item) for item in obj)
        else:
            return obj


class Email(MyBaseModel):
    """Represents an email message."""

    uid: str
    subject: str
    sender: str
    date: datetime
    body_text: str
    body_html: str | None = None


class TargetArticle(MyBaseModel):
    """A single transformed article in the target language."""

    title: str
    source: str
    date: str
    content: str
    glossary: dict[str, str]


class TargetEmailContent(MyBaseModel):
    """Full structured LLM response for the learning digest email."""

    introduction: str
    articles: list[TargetArticle]


class EmailChunk(MyBaseModel):
    """A single ordered text chunk from a source email."""

    chunk_id: UUID
    text: str


class ChunkedSourceEmail(MyBaseModel):
    """Email split into ordered text chunks for LLM processing."""

    email_id: UUID
    sender: str
    sender_name: str
    email_subject: str
    email_contents: list[EmailChunk]


class SourceArticleDescriptor(MyBaseModel):
    """A single topic extracted from a source email by the LLM."""

    article_id: UUID = Field(default_factory=uuid4)
    article_email: UUID | None = None  # set by pipeline after parsing, not by LLM
    title: str
    content_locations: list[UUID]
    tags: list[str]


class TopicExtractionResponse(MyBaseModel):
    """Wrapper for the stage-2 LLM response (topic extraction)."""

    articles: list[SourceArticleDescriptor]


class CurationResponse(MyBaseModel):
    """Stage-3 LLM response: selected article IDs."""

    selected_ids: list[UUID]


@dataclass
class SelectedArticle:
    """Stage-4 output: reconstructed article ready for transformation."""

    article_id: UUID
    title: str
    sender: str
    sender_name: str
    email_subject: str
    content: str
