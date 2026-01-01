import argparse
import logging
from pathlib import Path

from polyglot_pigeon.config import ConfigLoader, get_config

logger = logging.getLogger(__name__)


def setup_logger(level: int = logging.INFO) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        required=True,
        help="Path to the configuration file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=log_level)

    message = greet("World")
    logger.info(message)

    config_loader = ConfigLoader()
    config_loader.load(config_path=str(args.config))
    config = get_config()

    logger.debug(f"Loaded config: {config}")


if __name__ == "__main__":
    main()
