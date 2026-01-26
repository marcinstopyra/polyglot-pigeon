import tempfile
from pathlib import Path

import pytest
import yaml

from polyglot_pigeon.config import ConfigLoader, get_config
from polyglot_pigeon.models.configurations import (
    Config,
    Language,
    LanguageConfig,
    LLMConfig,
    LLMProvider,
    SourceEmailConfig,
    TargetEmailConfig,
)


def test_full_config():
    config = Config(
        source_email=SourceEmailConfig(
            address="source@example.com", app_password="secret123"
        ),
        llm=LLMConfig(provider="claude", api_key="sk-test"),
        language=LanguageConfig(target="German", level="b2"),  # Test different cases
        target_email=TargetEmailConfig(
            address="target@example.com",
            smtp_server="smtp.gmail.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="pass123",
        ),
    )
    assert config.model_dump() == {
        "language": {
            "level": "b2",
            "target": "german",
        },
        "llm": {
            "api_key": "sk-test",
            "max_tokens": 4096,
            "model": None,
            "provider": "claude",
            "temperature": 0.7,
        },
        "logging": {
            "file": "logs/polyglot_pigeon.log",
            "level": "INFO",
        },
        "schedule": {
            "time": "12:00",
            "timezone": "UTC",
        },
        "source_email": {
            "address": "source@example.com",
            "app_password": "secret123",
            "fetch_days": 1,
            "imap_port": 993,
            "imap_server": "imap.gmail.com",
            "mark_as_read": True,
        },
        "target_email": {
            "address": "target@example.com",
            "sender_name": "Polyglot Pigeon",
            "smtp_password": "pass123",
            "smtp_port": 587,
            "smtp_server": "smtp.gmail.com",
            "smtp_user": "user@example.com",
        },
    }


class TestConfigLoader:
    """Test ConfigLoader singleton and loading functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        ConfigLoader._instance = None
        ConfigLoader._config = None
        yield
        ConfigLoader._instance = None
        ConfigLoader._config = None

    @pytest.fixture
    def valid_config_dict(self):
        return {
            "source_email": {
                "address": "source@example.com",
                "app_password": "secret123",
                "imap_server": "imap.gmail.com",
                "imap_port": 993,
                "fetch_days": 1,
                "mark_as_read": True,
            },
            "llm": {
                "provider": "CLAUDE",
                "api_key": "sk-test123",
                "model": "claude-3-opus-20240229",
                "max_tokens": 4096,
                "temperature": 0.7,
            },
            "language": {"target": "german", "level": "b2"},
            "target_email": {
                "address": "target@example.com",
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "user@example.com",
                "smtp_password": "pass123",
                "sender_name": "Polyglot Pigeon",
            },
            "schedule": {"time": "12:00", "timezone": "UTC"},
            "logging": {"level": "INFO", "file": "logs/polyglot_pigeon.log"},
        }

    @pytest.fixture
    def temp_config_file(self, valid_config_dict):
        """Create a temporary config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(valid_config_dict, f)
            temp_path = Path(f.name)

        yield temp_path

        if temp_path.exists():
            temp_path.unlink()

    def test_singleton_pattern(self):
        loader1 = ConfigLoader()
        loader2 = ConfigLoader()
        assert loader1 is loader2

    def test_load_from_file(self, temp_config_file):
        loader = ConfigLoader()
        config = loader.load(temp_config_file)

        assert isinstance(config, Config)
        assert config.source_email.address == "source@example.com"
        assert config.llm.provider == LLMProvider.CLAUDE
        assert config.language.target == Language.GERMAN

    def test_load_caches_config(self, temp_config_file):
        loader = ConfigLoader()
        config1 = loader.load(temp_config_file)
        config2 = loader.load(temp_config_file)

        assert config1 is config2

    def test_config_property(self, temp_config_file):
        loader = ConfigLoader()
        loader.load(temp_config_file)

        config = loader.config
        assert isinstance(config, Config)

    def test_config_property_auto_loads(self, temp_config_file, monkeypatch):
        # Mock _find_config_file to return our temp file
        def mock_find():
            return temp_config_file

        loader = ConfigLoader()
        monkeypatch.setattr(loader, "_find_config_file", mock_find)

        config = loader.config
        assert isinstance(config, Config)

    def test_reload_forces_new_load(self, temp_config_file):
        loader = ConfigLoader()
        config1 = loader.load(temp_config_file)
        config2 = loader.reload(temp_config_file)

        # They should be different instances
        assert config1 is not config2
        # But have the same data
        assert config1.model_dump() == config2.model_dump()

    def test_file_not_found_raises_error(self):
        loader = ConfigLoader()

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load("/nonexistent/path/config.yaml")

        assert "Config file not found" in str(exc_info.value)
        assert "config.example.yaml" in str(exc_info.value)

    def test_get_config_function(self, temp_config_file, monkeypatch):
        # Mock _find_config_file to return our temp file
        def mock_find(self):
            return temp_config_file

        monkeypatch.setattr(ConfigLoader, "_find_config_file", mock_find)

        config = get_config()
        assert isinstance(config, Config)

    def test_find_config_file_search_paths(self, tmp_path, monkeypatch):
        # Create a config file in tmp_path
        config_file = tmp_path / "config.yaml"
        config_file.write_text("test: data")

        # Mock Path.cwd() to return tmp_path
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

        loader = ConfigLoader()
        found_path = loader._find_config_file()

        assert found_path == config_file

    def test_invalid_yaml_raises_error(self, tmp_path):
        invalid_file = tmp_path / "invalid.yaml"
        invalid_file.write_text("source_email: {address: 'test'")  # Invalid YAML

        loader = ConfigLoader()

        with pytest.raises(yaml.YAMLError):
            loader.load(invalid_file)

    def test_missing_required_fields_raises_validation_error(self, tmp_path):
        incomplete_file = tmp_path / "incomplete.yaml"
        incomplete_file.write_text(
            yaml.dump(
                {
                    "source_email": {
                        "address": "test@example.com"
                        # Missing app_password
                    }
                }
            )
        )

        loader = ConfigLoader()

        with pytest.raises(Exception):  # Pydantic ValidationError
            loader.load(incomplete_file)

    def test_minimal_valid_config(self, tmp_path):
        minimal_config = {
            "source_email": {
                "address": "source@example.com",
                "app_password": "secret123",
            },
            "llm": {"provider": "clAUde", "api_key": "sk-test"},
            "language": {"target": "German", "level": "b2"},
            "target_email": {
                "address": "target@example.com",
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "user@example.com",
                "smtp_password": "pass123",
            },
        }

        config_file = tmp_path / "minimal.yaml"
        config_file.write_text(yaml.dump(minimal_config))

        loader = ConfigLoader()
        config = loader.load(config_file)

        assert config.schedule.time == "12:00"  # Default value
        assert config.logging.level == "INFO"  # Default value
