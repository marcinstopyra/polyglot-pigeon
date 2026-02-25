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
        from polyglot_pigeon.content import ContentCleaner
        from polyglot_pigeon.llm import create_llm_client
        from polyglot_pigeon.llm.models import LLMMessage, MessageRole
        from polyglot_pigeon.mail import EmailSender
        from polyglot_pigeon.prompts import PromptManager

        if not emails:
            logger.info("No emails to process")
            return ProcessingResult(0, 0, [])

        # Step 1: Clean emails
        cleaned = ContentCleaner().clean(emails)
        if not cleaned:
            logger.warning("No emails had content after cleaning")
            return ProcessingResult(len(emails), 0, [])

        # Step 2: Format all cleaned content into a single string
        content_parts = [
            f"Subject: {e.subject}\nFrom: {e.sender}\n\n{e.body}" for e in cleaned
        ]
        combined_content = "\n\n---\n\n".join(content_parts)

        # Step 3: Build prompts
        lang = self.config.language
        known_language = lang.known.name.title()
        target_language = lang.target.name.title()
        level = lang.level.name

        prompts = PromptManager()
        language_extra = prompts.get("language_extra")
        article_structure_extra = prompts.get("article_structure_extra")

        system_prompt = prompts.get(
            "system",
            known_language=known_language,
            target_language=target_language,
            level=level,
            language_extra=language_extra,
            article_structure_extra=article_structure_extra,
        )
        user_prompt = prompts.get("transform_user", content=combined_content)

        try:
            llm_client = create_llm_client(self.config.llm)

            # Step 4: First LLM call — transform content to learning material
            logger.info(f"Transforming {len(cleaned)} articles via LLM")
            transform_response = llm_client.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                    LLMMessage(role=MessageRole.USER, content=user_prompt),
                ]
            )
            articles_text = transform_response.content

            # Step 5: Second LLM call — generate introduction
            intro_system = prompts.get(
                "introduction_system",
                target_language=target_language,
                level=level,
                language_extra=language_extra,
            )
            intro_user = prompts.get("introduction_user", articles=articles_text)
            intro_response = llm_client.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=intro_system),
                    LLMMessage(role=MessageRole.USER, content=intro_user),
                ]
            )
            introduction = intro_response.content

            # Step 6: Compose final email body
            body = f"{introduction}\n\n## Articles:\n\n{articles_text}"
            subject = f"Your {target_language} learning digest"

            # Step 7: Send
            with EmailSender(self.config.target_email) as sender:
                sender.send(
                    to=self.config.target_email.address,
                    subject=subject,
                    body_text=body,
                )

            logger.info(
                f"Sent digest with {len(cleaned)} articles to"
                f" {self.config.target_email.address}"
            )
            return ProcessingResult(
                emails_processed=len(emails),
                emails_sent=1,
                errors=[],
            )

        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            logger.error(error_msg)
            return ProcessingResult(
                emails_processed=len(emails),
                emails_sent=0,
                errors=[error_msg],
            )
