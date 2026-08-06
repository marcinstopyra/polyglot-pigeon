"""Tests for the env-based settings that replaced the ConfigLoader singleton.

Every test here takes the `clean_env` fixture, which strips the settings
variables from the environment and moves the working directory somewhere
without a `.env`. Without it these assertions would depend on the machine
running them.
"""

import logging
import pathlib
import re

import pytest
from pydantic import ValidationError

from polyglot_pigeon.shared.config import (
    BotSettings,
    ControllerSettings,
    CourierSettings,
    DatabaseSettings,
    Environment,
    IngestSettings,
    MissingSettingsError,
    ServiceSettings,
    SingleTenantSettings,
)
from polyglot_pigeon.shared.models.configurations import Language, LanguageLevel
from tests.unit_tests.conftest import env_aliases

IMAP_ENV = {
    "IMAP_ADDRESS": "source@example.com",
    "IMAP_PASSWORD": "imap-secret",
}
SMTP_ENV = {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_USER": "sender@example.com",
    "SMTP_PASSWORD": "smtp-secret",
}
LLM_ENV = {
    "LLM_API_KEY": "sk-test-secret",
    "LLM_MODEL": "claude-haiku-4-5-20251001",
}
USER_ENV = {
    "USER_TARGET_EMAIL": "learner@example.com",
    "USER_KNOWN_LANGUAGE": "english",
    "USER_TARGET_LANGUAGE": "german",
    "USER_LANGUAGE_LEVEL": "b1",
}


def set_env(clean_env, *mappings: dict[str, str]) -> None:
    for mapping in mappings:
        for key, value in mapping.items():
            clean_env.setenv(key, value)


# ── Fail-fast on missing variables ────────────────────────────────────────────


class TestMissingRequiredVariables:
    """A misconfigured process must die at startup, naming the variable."""

    @pytest.mark.parametrize(
        ("settings_cls", "env", "missing"),
        [
            (IngestSettings, {"IMAP_ADDRESS": "a@b.com"}, "IMAP_PASSWORD"),
            (IngestSettings, {"IMAP_PASSWORD": "x"}, "IMAP_ADDRESS"),
            (CourierSettings, {"SMTP_SERVER": "s", "SMTP_USER": "u"}, "SMTP_PASSWORD"),
            (ControllerSettings, {"LLM_MODEL": "m"}, "LLM_API_KEY"),
            (ControllerSettings, {"LLM_API_KEY": "k"}, "LLM_MODEL"),
            (BotSettings, {}, "TELEGRAM_BOT_TOKEN"),
        ],
    )
    def test_names_the_missing_variable(self, clean_env, settings_cls, env, missing):
        set_env(clean_env, env)

        with pytest.raises(MissingSettingsError) as exc_info:
            settings_cls()

        assert missing in str(exc_info.value)

    def test_error_names_the_env_var_not_the_field(self, clean_env):
        """`IMAP_PASSWORD` is actionable for an operator; `password` is not.

        `env_prefix` alone reports the bare field name, so this is the
        assertion that keeps `MissingSettingsError` earning its place.
        """
        set_env(clean_env, {"IMAP_ADDRESS": "a@b.com"})

        with pytest.raises(MissingSettingsError) as exc_info:
            IngestSettings()

        message = str(exc_info.value)
        assert "IMAP_PASSWORD" in message
        assert "password" not in message.replace("IMAP_PASSWORD", "")

    def test_complete_environment_constructs(self, clean_env):
        set_env(clean_env, IMAP_ENV)

        settings = IngestSettings()

        assert settings.imap.address == "source@example.com"
        assert settings.imap.port == 993  # default preserved


# ── Secrets never render ──────────────────────────────────────────────────────


class TestSecretsAreNotRenderable:
    SECRET_VALUES = ("imap-secret", "smtp-secret", "sk-test-secret", "db-secret")

    @pytest.fixture
    def full_settings(self, clean_env) -> SingleTenantSettings:
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV, USER_ENV)
        clean_env.setenv("DB_PASSWORD", "db-secret")
        return SingleTenantSettings()

    @pytest.mark.parametrize("render", [repr, str])
    def test_rendering_hides_every_secret(self, full_settings, render):
        rendered = render(full_settings)

        for secret in self.SECRET_VALUES:
            assert secret not in rendered
        assert "**********" in rendered

    def test_log_output_hides_secrets(self, full_settings, caplog):
        with caplog.at_level(logging.DEBUG):
            logging.getLogger("test").debug("settings: %r", full_settings)

        for secret in self.SECRET_VALUES:
            assert secret not in caplog.text

    def test_model_dump_hides_secrets(self, full_settings):
        """Serialisation is the other route a secret reaches a log line."""
        dumped = str(full_settings.model_dump())

        for secret in self.SECRET_VALUES:
            assert secret not in dumped

    def test_secret_is_still_retrievable(self, full_settings):
        assert full_settings.llm.api_key.get_secret_value() == "sk-test-secret"


# ── Services only know their own credentials ──────────────────────────────────


class TestServiceIsolation:
    """A service cannot leak a credential it was never handed."""

    def test_ingest_has_no_llm_credentials(self, clean_env):
        set_env(clean_env, IMAP_ENV, LLM_ENV)

        settings = IngestSettings()

        assert not hasattr(settings, "llm")
        assert "sk-test-secret" not in repr(settings)

    def test_controller_has_no_imap_credentials(self, clean_env):
        set_env(clean_env, IMAP_ENV, LLM_ENV)

        settings = ControllerSettings()

        assert not hasattr(settings, "imap")
        assert "source@example.com" not in repr(settings)

    def test_courier_has_no_llm_or_imap_credentials(self, clean_env):
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV)

        settings = CourierSettings()

        assert not hasattr(settings, "llm")
        assert not hasattr(settings, "imap")

    def test_courier_does_not_own_the_recipient(self, clean_env):
        """Who receives a digest is a user's property, not the relay's."""
        set_env(clean_env, SMTP_ENV)

        settings = CourierSettings()

        assert not hasattr(settings.smtp, "address")

    def test_every_service_shares_the_common_settings(self, clean_env):
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV)
        clean_env.setenv("TELEGRAM_BOT_TOKEN", "tg-token")
        clean_env.setenv("LOG_LEVEL", "DEBUG")

        for settings_cls in (
            IngestSettings,
            CourierSettings,
            ControllerSettings,
            BotSettings,
        ):
            settings = settings_cls()
            assert settings.log_level == "DEBUG"
            assert settings.database.name == "polyglot"


# ── Database settings ─────────────────────────────────────────────────────────


class TestDatabaseSettings:
    def test_defaults_match_docker_compose(self, clean_env):
        settings = DatabaseSettings()

        assert settings.url == (
            "mysql+pymysql://polyglot:polyglot@localhost:3306/polyglot?charset=utf8mb4"
        )

    def test_reads_db_env_vars(self, clean_env):
        set_env(
            clean_env,
            {
                "DB_HOST": "db",
                "DB_PORT": "3307",
                "DB_USER": "app",
                "DB_PASSWORD": "s3cr3t",
                "DB_NAME": "pigeon",
            },
        )

        settings = DatabaseSettings()

        assert settings.url == (
            "mysql+pymysql://app:s3cr3t@db:3307/pigeon?charset=utf8mb4"
        )

    def test_special_characters_in_password_are_encoded(self, clean_env):
        set_env(clean_env, {"DB_PASSWORD": "p@ss:w/rd"})

        settings = DatabaseSettings()

        assert "p%40ss%3Aw%2Frd" in settings.url
        assert "p@ss:w/rd" not in settings.url

    def test_bare_user_env_var_does_not_leak_into_db_user(self, clean_env):
        """Regression: `DB_USER` was being read from `USER`.

        `populate_by_name` made pydantic-settings match a field by name as well
        as by prefix, so `user` matched `USER` — the Unix username, set in
        essentially every shell and container. The connection string came out
        as the logged-in operator instead of `polyglot`, and the resulting
        `Access denied` pointed at MySQL rather than at the config.

        `clean_env` deliberately does not strip bare `USER`, so this asserts
        against the real conditions the bug appeared under.
        """
        clean_env.setenv("USER", "whoever-is-logged-in")

        settings = DatabaseSettings()

        assert settings.user == "polyglot"
        assert "whoever-is-logged-in" not in settings.url

    def test_password_is_not_rendered(self, clean_env):
        set_env(clean_env, {"DB_PASSWORD": "s3cr3t"})

        settings = DatabaseSettings()

        assert "s3cr3t" not in repr(settings)

    def test_development_default_password_is_refused_in_production(self, clean_env):
        set_env(clean_env, IMAP_ENV)
        clean_env.setenv("ENVIRONMENT", "production")

        with pytest.raises(ValidationError) as exc_info:
            IngestSettings()

        assert "DB_PASSWORD" in str(exc_info.value)

    def test_explicit_password_is_accepted_in_production(self, clean_env):
        set_env(clean_env, IMAP_ENV)
        clean_env.setenv("ENVIRONMENT", "production")
        clean_env.setenv("DB_PASSWORD", "a-real-password")

        settings = IngestSettings()

        assert settings.environment is Environment.PRODUCTION

    def test_development_default_password_is_allowed_in_development(self, clean_env):
        set_env(clean_env, IMAP_ENV)

        settings = IngestSettings()

        assert settings.environment is Environment.DEVELOPMENT
        assert settings.database.password.get_secret_value() == "polyglot"


# ── .env.example stays in step with the code ──────────────────────────────────


def test_env_example_documents_every_variable():
    """`.env.example` is the list a fresh clone starts from — so it must be complete.

    With `env_prefix` the variable names are derived, not written down, which
    makes them easy to add without documenting. This closes that gap: every
    variable the settings classes read has a line in `.env.example`, and every
    line in `.env.example` is read by something.
    """
    declared: set[str] = set()
    for settings_cls in (
        BotSettings,
        ControllerSettings,
        CourierSettings,
        IngestSettings,
        SingleTenantSettings,
    ):
        declared |= env_aliases(settings_cls)

    example = pathlib.Path(__file__).parents[2] / ".env.example"
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example.read_text(), re.M))

    assert declared - documented == set(), "read by the code, missing from .env.example"
    # DB_ROOT_PASSWORD is consumed by docker-compose for the MySQL container
    # itself, never by the application.
    assert documented - declared == {"DB_ROOT_PASSWORD"}


# ── No module-level settings object ───────────────────────────────────────────


def test_no_module_level_settings_instance():
    """The singleton is gone: importing the package constructs nothing."""
    import polyglot_pigeon.shared.config as config_module

    instances = [
        name
        for name, value in vars(config_module).items()
        if isinstance(value, ServiceSettings | DatabaseSettings)
    ]
    assert instances == []


# ── The single-tenant bridge to the legacy Config ─────────────────────────────


class TestSingleTenantSettings:
    @pytest.fixture
    def settings(self, clean_env) -> SingleTenantSettings:
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV, USER_ENV)
        return SingleTenantSettings()

    def test_language_names_parse_case_insensitively(self, clean_env):
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV, USER_ENV)
        clean_env.setenv("USER_TARGET_LANGUAGE", "SPANISH")
        clean_env.setenv("USER_LANGUAGE_LEVEL", "C1")

        settings = SingleTenantSettings()

        assert settings.user.target_language is Language.SPANISH
        assert settings.user.language_level is LanguageLevel.C1

    def test_unknown_language_is_rejected(self, clean_env):
        """A bad value is not a missing one: pydantic reports it, unwrapped."""
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV, USER_ENV)
        clean_env.setenv("USER_TARGET_LANGUAGE", "klingon")

        with pytest.raises(ValidationError) as exc_info:
            SingleTenantSettings()

        message = str(exc_info.value)
        assert "target_language" in message
        assert "klingon" in message

    def test_to_config_unwraps_secrets_for_the_clients(self, settings):
        config = settings.to_config()

        assert config.source_email.app_password == "imap-secret"
        assert config.target_email.smtp_password == "smtp-secret"
        assert config.llm.api_key == "sk-test-secret"

    def test_to_config_maps_the_user_fields(self, settings):
        config = settings.to_config()

        assert config.target_email.address == "learner@example.com"
        assert config.language.known is Language.ENGLISH
        assert config.language.target is Language.GERMAN
        assert config.language.level is LanguageLevel.B1

    def test_to_config_carries_defaults_through(self, settings):
        config = settings.to_config()

        assert config.source_email.imap_server == "imap.gmail.com"
        assert config.target_email.smtp_port == 587
        assert config.schedule.timezone == "UTC"
        assert config.pipeline.max_articles_in_final_email == 7

    def test_to_config_reflects_overrides(self, clean_env):
        set_env(clean_env, IMAP_ENV, SMTP_ENV, LLM_ENV, USER_ENV)
        clean_env.setenv("USER_TIMEZONE", "Europe/Warsaw")
        clean_env.setenv("USER_SEND_TIME", "08:00")
        clean_env.setenv("PIPELINE_MAX_ARTICLES", "3")
        clean_env.setenv("IMAP_FETCH_DAYS", "5")

        config = SingleTenantSettings().to_config()

        assert config.schedule.timezone == "Europe/Warsaw"
        assert config.schedule.time == "08:00"
        assert config.pipeline.max_articles_in_final_email == 3
        assert config.source_email.fetch_days == 5

    def test_log_file_defaults_to_console_only(self, settings):
        assert settings.log_file is None
        assert settings.to_config().logging.file is None
