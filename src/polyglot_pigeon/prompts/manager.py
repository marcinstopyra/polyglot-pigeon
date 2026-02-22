"""Prompt manager with default prompts and partial override support."""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"


class PromptManager:
    """Loads default prompts and merges optional user overrides.

    Usage:
        manager = PromptManager()
        prompt = manager.get("system", target_language="German", level="B1", ...)
    """

    def __init__(self, overrides_path: Path | str | None = None):
        self._prompts = self._load_defaults()

        if overrides_path is not None:
            overrides = self._load_yaml(Path(overrides_path))
            self._prompts.update(overrides)
            logger.info(f"Loaded prompt overrides from {overrides_path}")

    def get(self, name: str, **kwargs: str) -> str:
        """Get a prompt by name with placeholders filled.

        Args:
            name: The prompt key (e.g. "system", "transform_user").
            **kwargs: Values to substitute into placeholders.

        Returns:
            The prompt string with placeholders replaced.

        Raises:
            KeyError: If the prompt name is not found.
        """
        if name not in self._prompts:
            raise KeyError(
                f"Prompt '{name}' not found. Available: {list(self._prompts.keys())}"
            )

        template = self._prompts[name]
        return template.format(**kwargs)

    def list_prompts(self) -> list[str]:
        """Return all available prompt names."""
        return list(self._prompts.keys())

    def _load_defaults(self) -> dict[str, str]:
        return self._load_yaml(_DEFAULTS_PATH)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, str]:
        with open(path) as f:
            return yaml.safe_load(f)
