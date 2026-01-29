"""Tests for the scheduler module."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from polyglot_pigeon.models.configurations import (
    Config,
    Language,
    LanguageConfig,
    LanguageLevel,
    LLMConfig,
    LLMProvider,
    ScheduleConfig,
    SourceEmailConfig,
    TargetEmailConfig,
)
from polyglot_pigeon.models.models import Email
from polyglot_pigeon.scheduler import (
    EmailScheduler,
    PlaceholderPipeline,
    ProcessingResult,
)


class TestProcessingResult:
    """Test ProcessingResult dataclass."""

    def test_create_result(self):
        result = ProcessingResult(
            emails_processed=5,
            emails_sent=4,
            errors=["error1"],
        )

        assert result.emails_processed == 5
        assert result.emails_sent == 4
        assert result.errors == ["error1"]

    def test_create_empty_result(self):
        result = ProcessingResult(
            emails_processed=0,
            emails_sent=0,
            errors=[],
        )

        assert result.emails_processed == 0
        assert result.errors == []


class TestPlaceholderPipeline:
    """Test PlaceholderPipeline."""

    def test_process_empty_list(self):
        pipeline = PlaceholderPipeline()
        result = pipeline.process([])

        assert result.emails_processed == 0
        assert result.emails_sent == 0
        assert result.errors == []

    def test_process_logs_emails(self):
        pipeline = PlaceholderPipeline()
        mock_emails = [
            Email(
                uid="1",
                subject="Test Subject",
                sender="test@example.com",
                date=datetime.now(),
                body_text="Test body",
            ),
            Email(
                uid="2",
                subject="Another Subject",
                sender="another@example.com",
                date=datetime.now(),
                body_text="Another body",
            ),
        ]

        result = pipeline.process(mock_emails)

        assert result.emails_processed == 2
        assert result.emails_sent == 0
        assert result.errors == []


class TestEmailScheduler:
    """Test EmailScheduler."""

    @pytest.fixture
    def mock_config(self):
        return Config(
            source_email=SourceEmailConfig(
                address="source@example.com",
                app_password="password123",
                imap_server="imap.example.com",
                imap_port=993,
                fetch_days=1,
                mark_as_read=True,
            ),
            llm=LLMConfig(
                provider=LLMProvider.CLAUDE,
                api_key="test-api-key",
            ),
            language=LanguageConfig(
                target=Language.GERMAN,
                level=LanguageLevel.B1,
            ),
            target_email=TargetEmailConfig(
                address="target@example.com",
                smtp_server="smtp.example.com",
                smtp_port=587,
                smtp_user="user",
                smtp_password="pass",
            ),
            schedule=ScheduleConfig(
                time="12:00",
                timezone="UTC",
                enabled=True,
            ),
        )

    @pytest.fixture
    def mock_pipeline(self):
        pipeline = MagicMock()
        pipeline.process.return_value = ProcessingResult(
            emails_processed=2,
            emails_sent=2,
            errors=[],
        )
        return pipeline

    @pytest.fixture
    def sample_emails(self):
        return [
            Email(
                uid="1",
                subject="Newsletter 1",
                sender="news@example.com",
                date=datetime.now(),
                body_text="Content 1",
            ),
            Email(
                uid="2",
                subject="Newsletter 2",
                sender="news@example.com",
                date=datetime.now(),
                body_text="Content 2",
            ),
        ]

    def test_init_with_config_and_pipeline(self, mock_config, mock_pipeline):
        scheduler = EmailScheduler(config=mock_config, pipeline=mock_pipeline)

        assert scheduler.config == mock_config
        assert scheduler.pipeline == mock_pipeline
        assert scheduler._running is False

    def test_init_with_defaults(self, mock_config):
        with patch(
            "polyglot_pigeon.scheduler.scheduler.get_config", return_value=mock_config
        ):
            scheduler = EmailScheduler()

            assert scheduler.config == mock_config
            assert isinstance(scheduler.pipeline, PlaceholderPipeline)

    def test_get_timezone(self, mock_config):
        scheduler = EmailScheduler(config=mock_config)

        tz = scheduler._get_timezone()

        assert tz == ZoneInfo("UTC")

    def test_get_timezone_non_utc(self, mock_config):
        mock_config.schedule.timezone = "Europe/Warsaw"
        scheduler = EmailScheduler(config=mock_config)

        tz = scheduler._get_timezone()

        assert tz == ZoneInfo("Europe/Warsaw")

    def test_get_current_time_in_tz(self, mock_config):
        scheduler = EmailScheduler(config=mock_config)

        current_time = scheduler._get_current_time_in_tz()

        assert current_time.tzinfo == ZoneInfo("UTC")

    def test_run_once_fetches_and_processes(
        self, mock_config, mock_pipeline, sample_emails
    ):
        scheduler = EmailScheduler(config=mock_config, pipeline=mock_pipeline)

        with patch.object(
            scheduler, "_fetch_emails", return_value=sample_emails
        ) as mock_fetch:
            with patch.object(scheduler, "_mark_emails_processed") as mock_mark:
                result = scheduler.run_once()

        mock_fetch.assert_called_once()
        mock_pipeline.process.assert_called_once_with(sample_emails)
        mock_mark.assert_called_once_with(["1", "2"])
        assert result.emails_processed == 2

    def test_run_once_no_emails(self, mock_config, mock_pipeline):
        mock_pipeline.process.return_value = ProcessingResult(0, 0, [])
        scheduler = EmailScheduler(config=mock_config, pipeline=mock_pipeline)

        with patch.object(scheduler, "_fetch_emails", return_value=[]):
            with patch.object(scheduler, "_mark_emails_processed") as mock_mark:
                result = scheduler.run_once()

        assert result.emails_processed == 0
        mock_mark.assert_not_called()

    def test_run_once_skips_marking_if_disabled(
        self, mock_config, mock_pipeline, sample_emails
    ):
        mock_config.source_email.mark_as_read = False
        scheduler = EmailScheduler(config=mock_config, pipeline=mock_pipeline)

        with patch.object(scheduler, "_fetch_emails", return_value=sample_emails):
            with patch.object(scheduler, "_mark_emails_processed") as mock_mark:
                scheduler.run_once()

        mock_mark.assert_not_called()

    def test_start_returns_if_disabled(self, mock_config):
        mock_config.schedule.enabled = False
        scheduler = EmailScheduler(config=mock_config)

        scheduler.start()

        assert scheduler._running is False

    def test_stop_sets_running_false(self, mock_config):
        scheduler = EmailScheduler(config=mock_config)
        scheduler._running = True

        scheduler.stop()

        assert scheduler._running is False


class TestScheduleConfig:
    """Test ScheduleConfig."""

    def test_defaults(self):
        config = ScheduleConfig()

        assert config.time == "12:00"
        assert config.timezone == "UTC"
        assert config.enabled is True

    def test_custom_values(self):
        config = ScheduleConfig(
            time="08:30",
            timezone="Europe/Warsaw",
            enabled=False,
        )

        assert config.time == "08:30"
        assert config.timezone == "Europe/Warsaw"
        assert config.enabled is False
