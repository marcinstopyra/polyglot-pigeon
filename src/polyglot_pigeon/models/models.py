from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, model_serializer, model_validator


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
