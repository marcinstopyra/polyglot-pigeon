"""Processing pipeline interface and implementations."""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import ValidationError

from polyglot_pigeon.config import get_config
from polyglot_pigeon.content import ContentCleaner
from polyglot_pigeon.llm import create_llm_client
from polyglot_pigeon.llm.models import LLMMessage, MessageRole
from polyglot_pigeon.mail import EmailSender
from polyglot_pigeon.models.models import Email, TargetEmailContent
from polyglot_pigeon.prompts import PromptManager

logger = logging.getLogger(__name__)

MAX_JSON_RETRIES = 3

_HTML_STYLE = (
    "body{font-family:Georgia,'Times New Roman',serif;"
    "max-width:680px;margin:0 auto;padding:20px;line-height:1.7;color:#333;}"
    "h1{font-size:1.8em;color:#1a1a2e;margin-top:0;}"
    "h2{font-size:1.4em;color:#1a1a2e;"
    "border-bottom:2px solid #ddd;padding-bottom:6px;margin-top:2em;}"
    "h3{font-size:1.1em;color:#1a1a2e;}"
    "hr{border:none;border-top:2px solid #ddd;margin:24px 0;}"
    "strong{color:#1a1a2e;}em{color:#555;}p{margin:0.7em 0;}"
)


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _parse_json_with_retry(
    raw: str,
    llm_client,
    original_messages: list,
    fix_prompt: str,
    max_retries: int = MAX_JSON_RETRIES,
) -> TargetEmailContent:
    """Parse LLM response as TargetEmailContent, retrying via LLM if invalid.

    Strategy:
    1. Strip markdown fences and attempt parse.
    2. For each retry: send the bad response back to the LLM with the fix
       prompt, then attempt parse again.
    3. If all retries exhausted, raise ValueError.
    """
    def _try_parse(text: str) -> TargetEmailContent | None:
        try:
            return TargetEmailContent.model_validate_json(_strip_json_fences(text))
        except (json.JSONDecodeError, ValidationError, ValueError):
            return None

    # Initial attempt
    result = _try_parse(raw)
    if result is not None:
        return result

    # Retry loop — ask LLM to fix its own output
    current = raw
    for attempt in range(max_retries):
        logger.warning(f"JSON parse failed, retry {attempt + 1}/{max_retries}")
        fix_response = llm_client.complete(
            [
                *original_messages,
                LLMMessage(role=MessageRole.ASSISTANT, content=current),
                LLMMessage(role=MessageRole.USER, content=fix_prompt),
            ]
        )
        current = fix_response.content
        result = _try_parse(current)
        if result is not None:
            return result
    else:
        raise ValueError(
            f"Failed to parse LLM response as valid JSON after {max_retries} retries"
        )


def _render_html(content: TargetEmailContent) -> str:
    """Render a TargetEmailContent as a styled HTML email document."""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<style>{_HTML_STYLE}</style></head><body>",
        f"<p>{content.introduction}</p>",
        "<h2>Articles</h2>",
    ]
    for i, article in enumerate(content.articles):
        if i > 0:
            parts.append("<hr>")  # separator between articles
        parts.append(f"<h3>{article.title}</h3>")
        parts.append(f"<p><em>{article.source} &middot; {article.date}</em></p>")
        parts.append(f"<p>{article.content}</p>")
        if article.glossary:
            parts.append("<hr>")  # separator between article content and glossary
            for word, translation in article.glossary.items():
                parts.append(f"<p><strong>{word}</strong>: {translation}</p>")
    parts.append("</body></html>")
    return "".join(parts)


def _render_text(content: TargetEmailContent) -> str:
    """Render a TargetEmailContent as a plain-text email body."""
    parts = [content.introduction, "", "## Articles:", ""]
    for i, article in enumerate(content.articles):
        if i > 0:
            parts.append("---")
            parts.append("")
        parts.append(f"## {article.title}")
        parts.append(f"{article.source} · {article.date}")
        parts.append("")
        parts.append(article.content)
        parts.append("")
        if article.glossary:
            parts.append("---")
            for word, translation in article.glossary.items():
                parts.append(f"**{word}**: {translation}")
            parts.append("")
    return "\n".join(parts)


@dataclass
class DigestContent:
    """Rendered digest ready to be sent as an email."""

    subject: str
    body_text: str
    body_html: str


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
    1. Transform content via LLM (returns structured JSON)
    2. Render JSON to HTML/text email
    3. Send to target email via SMTP
    """

    def __init__(self):
        self.config = get_config()

    def build_digest(self, emails: list[Email]) -> DigestContent:
        """Clean emails, call LLM, parse response, and render to email formats.

        Args:
            emails: Raw emails to transform into a learning digest.

        Returns:
            DigestContent with subject, plain-text body, and HTML body.

        Raises:
            ValueError: If no content remains after cleaning or JSON parsing fails.
        """
        cleaned = ContentCleaner().clean(emails)
        if not cleaned:
            raise ValueError("No emails had content after cleaning")

        content_parts = [
            f"Subject: {e.subject}\nFrom: {e.sender}\n\n{e.body}" for e in cleaned
        ]
        combined_content = "\n\n---\n\n".join(content_parts)

        lang = self.config.language
        known_language = lang.known.name.title()
        target_language = lang.target.name.title()
        level = lang.level.name

        prompts = PromptManager()
        language_extra = prompts.get("language_extra")
        article_structure_extra = prompts.get("article_structure_extra")
        json_schema = json.dumps(TargetEmailContent.model_json_schema(), indent=2)

        system_prompt = prompts.get(
            "system",
            known_language=known_language,
            target_language=target_language,
            level=level,
            language_extra=language_extra,
            article_structure_extra=article_structure_extra,
            json_schema=json_schema,
        )
        user_prompt = prompts.get("transform_user", content=combined_content)
        fix_prompt = prompts.get("json_fix", json_schema=json_schema)

        llm_client = create_llm_client(self.config.llm)
        logger.info(f"Transforming {len(cleaned)} articles via LLM")
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=user_prompt),
        ]
        transform_response = llm_client.complete(messages)

        parsed = _parse_json_with_retry(
            raw=transform_response.content,
            llm_client=llm_client,
            original_messages=messages,
            fix_prompt=fix_prompt,
        )

        return DigestContent(
            subject=f"Your {target_language} learning digest",
            body_text=_render_text(parsed),
            body_html=_render_html(parsed),
        )

    def send_target_email(self, digest: DigestContent) -> ProcessingResult:
        """Send a pre-built digest to the configured target email address.

        Args:
            digest: Rendered digest content to send.

        Returns:
            ProcessingResult indicating success or failure.
        """
        try:
            with EmailSender(self.config.target_email) as sender:
                sender.send(
                    to=self.config.target_email.address,
                    subject=digest.subject,
                    body_text=digest.body_text,
                    body_html=digest.body_html,
                )
            logger.info(f"Sent digest to {self.config.target_email.address}")
            return ProcessingResult(emails_processed=0, emails_sent=1, errors=[])
        except Exception as e:
            error_msg = f"Failed to send email: {e}"
            logger.error(error_msg)
            return ProcessingResult(emails_processed=0, emails_sent=0, errors=[error_msg])

    def process(self, emails: list[Email]) -> ProcessingResult:
        """Build and send a learning digest from a list of emails.

        Orchestrates build_digest() and send_target_email(). Use those methods
        directly when you need to intercept the digest before sending (e.g. dry-run).
        """
        if not emails:
            logger.info("No emails to process")
            return ProcessingResult(0, 0, [])

        try:
            digest = self.build_digest(emails)
        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            logger.error(error_msg)
            return ProcessingResult(
                emails_processed=len(emails), emails_sent=0, errors=[error_msg]
            )

        result = self.send_target_email(digest)
        result.emails_processed = len(emails)
        return result
