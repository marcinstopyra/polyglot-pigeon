"""Entry point: python -m polyglot_pigeon.services.bot"""

import logging

from polyglot_pigeon.shared.config import BotSettings

log = logging.getLogger(__name__)


def main() -> None:
    # Constructed here and passed down from here. Every variable this service
    # requires is validated now, so a misconfigured process dies at startup
    # rather than at its first send.
    settings = BotSettings()
    logging.basicConfig(level=settings.log_level)
    log.info("bot service starting in %s", settings.environment.value)


if __name__ == "__main__":
    main()
