"""Cron-like scheduler for email processing."""

import logging
import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import schedule

from polyglot_pigeon.config import get_config
from polyglot_pigeon.mail import EmailReader
from polyglot_pigeon.models.configurations import Config
from polyglot_pigeon.scheduler.pipeline import (
    Pipeline,
    PlaceholderPipeline,
    ProcessingResult,
)

logger = logging.getLogger(__name__)


class EmailScheduler:
    """
    Schedules and runs email processing at configured times.

    Uses the `schedule` library for cron-like scheduling with
    timezone support via Python's zoneinfo module.
    """

    def __init__(
        self,
        config: Config | None = None,
        pipeline: Pipeline | None = None,
    ):
        """
        Initialize the scheduler.

        Args:
            config: Application configuration. If None, loads from ConfigLoader.
            pipeline: Processing pipeline. If None, uses PlaceholderPipeline.
        """
        self.config = config or get_config()
        self.pipeline = pipeline or PlaceholderPipeline()
        self._running = False

    def _setup_signal_handlers(self) -> None:
        """Set up graceful shutdown handlers."""
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False

    def _get_timezone(self) -> ZoneInfo:
        """Get the configured timezone."""
        return ZoneInfo(self.config.schedule.timezone)

    def _get_current_time_in_tz(self) -> datetime:
        """Get current time in configured timezone."""
        return datetime.now(self._get_timezone())

    def run_once(self) -> ProcessingResult:
        """
        Run the processing pipeline once immediately.

        Returns:
            ProcessingResult from the pipeline
        """
        logger.info("Starting one-shot email processing")

        emails = self._fetch_emails()
        result = self.pipeline.process(emails)

        if result.emails_processed > 0 and self.config.source_email.mark_as_read:
            self._mark_emails_processed([e.uid for e in emails])

        logger.info(
            f"Processing complete: {result.emails_processed} processed, "
            f"{result.emails_sent} sent, {len(result.errors)} errors"
        )
        return result

    def _fetch_emails(self) -> list:
        """Fetch unread emails from source inbox."""
        with EmailReader(self.config.source_email) as reader:
            return reader.fetch_emails(unread_only=True)

    def _mark_emails_processed(self, uids: list[str]) -> None:
        """Mark emails as processed (read)."""
        with EmailReader(self.config.source_email) as reader:
            reader.mark_as_read(uids)
            logger.debug(f"Marked {len(uids)} emails as read")

    def _job(self) -> None:
        """Scheduled job wrapper."""
        logger.info(f"Scheduled job triggered at {self._get_current_time_in_tz()}")
        try:
            self.run_once()
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}", exc_info=True)

    def start(self) -> None:
        """
        Start the scheduler daemon.

        Runs indefinitely, checking the schedule every 30 seconds.
        Handles SIGINT and SIGTERM for graceful shutdown.
        """
        if not self.config.schedule.enabled:
            logger.warning("Scheduler is disabled in configuration")
            return

        self._setup_signal_handlers()

        schedule_time = self.config.schedule.time
        tz_name = self.config.schedule.timezone

        logger.info(f"Starting scheduler: {schedule_time} {tz_name}")
        logger.info(f"Current time in {tz_name}: {self._get_current_time_in_tz()}")

        schedule.every().day.at(schedule_time).do(self._job)

        self._running = True
        while self._running:
            schedule.run_pending()
            time.sleep(30)

        logger.info("Scheduler stopped")

    def stop(self) -> None:
        """Stop the scheduler daemon."""
        self._running = False
