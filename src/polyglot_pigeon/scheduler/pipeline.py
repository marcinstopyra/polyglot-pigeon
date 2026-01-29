"""Processing pipeline interface and implementations."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from polyglot_pigeon.models.models import Email

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a batch of emails."""

    emails_processed: int
    emails_sent: int
    errors: list[str]


class Pipeline(ABC):
    """Abstract base class for email processing pipelines."""

    @abstractmethod
    def process(self, emails: list[Email]) -> ProcessingResult:
        """
        Process a list of emails through the pipeline.

        Args:
            emails: List of emails to process

        Returns:
            ProcessingResult with statistics and errors
        """
        pass


class PlaceholderPipeline(Pipeline):
    """Placeholder pipeline that logs emails but does not process them."""

    def process(self, emails: list[Email]) -> ProcessingResult:
        """Log emails without actual processing (for development/testing)."""
        logger.info(f"PlaceholderPipeline: Would process {len(emails)} emails")
        for email in emails:
            logger.debug(f"  - {email.subject} from {email.sender}")

        return ProcessingResult(
            emails_processed=len(emails),
            emails_sent=0,
            errors=[],
        )


class EmailProcessingPipeline(Pipeline):
    """
    Full email processing pipeline.

    Workflow:
    1. Transform content via LLM
    2. Send to target email via SMTP
    """

    def __init__(self):
        from polyglot_pigeon.config import get_config

        self.config = get_config()

    def process(self, emails: list[Email]) -> ProcessingResult:
        """Process emails through LLM and send results."""
        from polyglot_pigeon.llm import create_llm_client

        errors = []
        emails_sent = 0

        if not emails:
            logger.info("No emails to process")
            return ProcessingResult(0, 0, [])

        llm_client = create_llm_client(self.config.llm)

        for email in emails:
            try:
                # TODO: Implement actual transformation logic
                # 1. Build prompt from email content + language config
                # 2. Call LLM for transformation
                # 3. Send transformed content via SMTP
                logger.info(f"Processing: {email.subject}")
                _ = llm_client  # Placeholder to avoid unused variable warning
                emails_sent += 1
            except Exception as e:
                error_msg = f"Failed to process {email.uid}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return ProcessingResult(
            emails_processed=len(emails),
            emails_sent=emails_sent,
            errors=errors,
        )
