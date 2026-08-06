import argparse
import functools
import logging
from pathlib import Path

from polyglot_pigeon.scheduler import EmailProcessingPipeline, EmailScheduler
from polyglot_pigeon.shared.config import SingleTenantSettings

log = logging.getLogger(__name__)


def setup_logger(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """Configure logging for the application."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )
    # Suppress verbose request/response body logging from HTTP client libraries
    for noisy in ("httpx", "httpcore", "anthropic", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PolyglotPigeon - Transform newsletters into language learning content"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a long-running daemon (scheduled processing)",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run processing once immediately and exit",
    )
    args = parser.parse_args()

    # Built here and nowhere else: every required variable is validated before
    # the first IMAP connection or LLM call, so a missing credential is a
    # startup failure naming the variable rather than an error hours later.
    settings = SingleTenantSettings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    setup_logger(level=log_level, log_file=settings.log_file)

    # Safe to log: every credential on a settings object is a SecretStr.
    log.debug(f"Loaded settings: {settings!r}")

    config = settings.to_config()
    scheduler = EmailScheduler(
        config=config,
        pipeline_factory=functools.partial(EmailProcessingPipeline, config),
    )

    if args.daemon:
        log.info("Starting in daemon mode")
        scheduler.start()
    elif args.run_once:
        log.info("Running one-shot processing")
        result = scheduler.run_once()
        if result.errors:
            log.error(f"Completed with {len(result.errors)} errors")
    else:
        log.info(
            "Use --daemon for scheduled processing or --run-once for immediate processing"
        )


if __name__ == "__main__":
    main()
