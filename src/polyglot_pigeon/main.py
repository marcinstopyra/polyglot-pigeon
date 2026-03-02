import argparse
import logging
from pathlib import Path

from polyglot_pigeon.config import ConfigLoader, get_config
from polyglot_pigeon.scheduler import EmailProcessingPipeline, EmailScheduler

logger = logging.getLogger(__name__)


def setup_logger(level: int = logging.INFO) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
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
        "-c",
        "--config",
        type=Path,
        required=True,
        help="Path to the configuration file",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=None,
        help="Path to prompt overrides YAML file (optional)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
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

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=log_level)

    config_loader = ConfigLoader()
    config_loader.load(config_path=str(args.config))
    config = get_config()

    logger.debug(f"Loaded config: {config}")

    pipeline = EmailProcessingPipeline(prompts_path=args.prompts)
    scheduler = EmailScheduler(config=config, pipeline=pipeline)

    if args.daemon:
        logger.info("Starting in daemon mode")
        scheduler.start()
    elif args.run_once:
        logger.info("Running one-shot processing")
        result = scheduler.run_once()
        if result.errors:
            logger.error(f"Completed with {len(result.errors)} errors")
    else:
        logger.info(
            "Use --daemon for scheduled processing or --run-once for immediate processing"
        )


if __name__ == "__main__":
    main()
