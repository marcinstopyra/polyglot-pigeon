from pathlib import Path

import yaml

from polyglot_pigeon.models.configurations import Config


class ConfigLoader:
    """Singleton configuration loader."""

    _instance: "ConfigLoader | None" = None
    _config: Config | None = None

    def __new__(cls) -> "ConfigLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: str | Path | None = None) -> Config:
        """Load configuration from YAML file."""
        if self._config is not None:
            return self._config

        if config_path is None:
            config_path = self._find_config_file()

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                "Copy config.example.yaml to config.yaml and fill in your values."
            )

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        self._config = Config(**raw)
        return self._config

    def _find_config_file(self) -> Path:
        """Search for config.yaml in common locations."""
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd().parent / "config.yaml",
            Path(__file__).parent.parent.parent.parent / "config.yaml",
        ]
        for path in search_paths:
            if path.exists():
                return path
        return search_paths[0]  # Return default for error message

    @property
    def config(self) -> Config:
        """Get loaded config, loading from default path if needed."""
        if self._config is None:
            self.load()
        return self._config

    def reload(self, config_path: str | Path | None = None) -> Config:
        """Force reload configuration."""
        self._config = None
        return self.load(config_path)


def get_config() -> Config:
    """Get the application configuration."""
    return ConfigLoader().config
