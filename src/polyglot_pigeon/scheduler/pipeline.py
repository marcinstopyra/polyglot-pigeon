"""Processing pipeline interface and implementations."""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytz
from jinja2 import Environment, FileSystemLoader
from pydantic import ValidationError

from polyglot_pigeon.config import get_config
from polyglot_pigeon.content import chunk_email
from polyglot_pigeon.llm import create_llm_client
from polyglot_pigeon.llm.models import LLMMessage, MessageRole
from polyglot_pigeon.mail import EmailSender, InlineImage
from polyglot_pigeon.models.models import (
    SourceArticleDescriptor,
    TopicExtractionResponse,
    CurationResponse,
    Email,
    MyBaseModel,
    SelectedArticle,
    ChunkedSourceEmail,
    TargetEmailContent,
)
from polyglot_pigeon.prompts import PromptManager

log = logging.getLogger(__name__)

MAX_JSON_RETRIES = 3

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_LOGO_PATH = _TEMPLATES_DIR / "logo.png"
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _parse_json_with_retry(
    raw: str,
    llm_client: Any,
    original_messages: list,
    fix_prompt: str,
    max_retries: int = MAX_JSON_RETRIES,
    model_class: type[MyBaseModel] = TargetEmailContent,
) -> Any:
    """Parse LLM response as a Pydantic model, retrying via LLM if invalid.

    Strategy:
    1. Strip markdown fences and attempt parse.
    2. For each retry: send the bad response back to the LLM with the fix
       prompt, then attempt parse again.
    3. If all retries exhausted, raise ValueError.
    """

    def _try_parse(text: str) -> Any | None:
        try:
            return model_class.model_validate_json(_strip_json_fences(text))
        except (json.JSONDecodeError, ValidationError, ValueError):
            return None

    # Initial attempt
    result = _try_parse(raw)
    if result is not None:
        return result

    # Retry loop — ask LLM to fix its own output
    current = raw
    for attempt in range(max_retries):
        log.warning(f"JSON parse failed, retry {attempt + 1}/{max_retries}")
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


def _render_html(
    content: TargetEmailContent,
    title: str,
    date: str,
    logo_cid: str | None,
) -> str:
    """Render a TargetEmailContent as a styled HTML email document."""
    template = _jinja_env.get_template("digest.html.j2")
    return template.render(content=content, title=title, date=date, logo_cid=logo_cid)


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
    inline_images: list[InlineImage] = field(default_factory=list)


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
        log.info(f"PlaceholderPipeline: Would process {len(emails)} emails")
        for email in emails:
            log.debug(f"  - {email.subject} from {email.sender}")

        return ProcessingResult(
            emails_processed=len(emails),
            emails_sent=0,
            errors=[],
        )


class EmailProcessingPipeline(Pipeline):
    """
    Full email processing pipeline.

    Workflow:
    1. Chunk emails into UUID-keyed text segments
    2. Extract topics per email via LLM
    3. Curate a diverse selection of articles via LLM
    4. Reconstruct raw content for selected articles (no LLM)
    5. Transform selected articles into learning digest via LLM
    6. Render and send via SMTP
    """

    def __init__(self, prompts_path: Path | None = None):
        self.config = get_config()
        self._prompts_path = prompts_path

    # ── Stage 1: Chunk emails ─────────────────────────────────────────────────

    def _chunk_emails(self, emails: list[Email]) -> list[ChunkedSourceEmail]:
        pipeline_cfg = self.config.pipeline
        return [
            chunk_email(
                email,
                min_chars=pipeline_cfg.min_chunk_chars,
                max_chunks=pipeline_cfg.max_chunks_per_email,
            )
            for email in emails
        ]

    # ── Stage 2: Extract topics per email ────────────────────────────────────

    def _extract_topics(
        self,
        source_list: list[ChunkedSourceEmail],
        llm_client: Any,
        prompts: PromptManager,
    ) -> list[SourceArticleDescriptor]:
        all_topics: list[SourceArticleDescriptor] = []
        json_schema = json.dumps(TopicExtractionResponse.model_json_schema(), indent=2)
        system_prompt = prompts.get("extract_topics_system", json_schema=json_schema)
        fix_prompt = prompts.get("json_fix", json_schema=json_schema)

        for source in source_list:
            email_contents_json = json.dumps(
                [{"chunk_id": str(c.chunk_id), "text": c.text} for c in source.email_contents],
                indent=2,
            )
            user_prompt = prompts.get(
                "extract_topics_user",
                sender_name=source.sender_name,
                email_subject=source.email_subject,
                email_contents_json=email_contents_json,
                json_schema=json_schema,
            )
            messages = [
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(role=MessageRole.USER, content=user_prompt),
            ]

            try:
                response = llm_client.complete(messages)
                topic_list = _parse_json_with_retry(
                    raw=response.content,
                    llm_client=llm_client,
                    original_messages=messages,
                    fix_prompt=fix_prompt,
                    model_class=TopicExtractionResponse,
                )
            except Exception as e:
                log.warning(
                    f"Topic extraction failed for '{source.email_subject}': {e}"
                )
                continue

            valid_chunk_ids = {c.chunk_id for c in source.email_contents}
            for topic in topic_list.articles:
                invalid = [
                    uid for uid in topic.content_locations if uid not in valid_chunk_ids
                ]
                if invalid:
                    log.warning(
                        f"Topic '{topic.title}' references {len(invalid)} unknown chunk "
                        f"UUIDs — dropping them"
                    )
                valid_locs = [
                    uid for uid in topic.content_locations if uid in valid_chunk_ids
                ]
                if valid_locs:
                    topic.content_locations = valid_locs
                    topic.article_email = source.email_id
                    all_topics.append(topic)
                else:
                    log.warning(
                        f"Topic '{topic.title}' has no valid content locations — skipping"
                    )

        return all_topics

    # ── Stage 3: Curate articles ──────────────────────────────────────────────

    def _curate_articles(
        self,
        topics: list[SourceArticleDescriptor],
        max_articles: int,
        llm_client: Any,
        prompts: PromptManager,
    ) -> list[UUID]:
        lang = self.config.language
        json_schema = json.dumps(CurationResponse.model_json_schema(), indent=2)

        articles_json = json.dumps(
            [
                {"article_id": str(t.article_id), "title": t.title, "tags": t.tags}
                for t in topics
            ],
            indent=2,
        )
        system_prompt = prompts.get(
            "curate_articles_system",
            max_articles=str(max_articles),
            target_language=lang.target.name.title(),
            known_language=lang.known.name.title(),
            json_schema=json_schema,
        )
        user_prompt = prompts.get(
            "curate_articles_user",
            articles_json=articles_json,
            max_articles=str(max_articles),
            json_schema=json_schema,
        )
        fix_prompt = prompts.get("json_fix", json_schema=json_schema)

        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=user_prompt),
        ]
        response = llm_client.complete(messages)
        curation = _parse_json_with_retry(
            raw=response.content,
            llm_client=llm_client,
            original_messages=messages,
            fix_prompt=fix_prompt,
            model_class=CurationResponse,
        )

        valid_ids = {t.article_id for t in topics}
        selected = [uid for uid in curation.selected_ids if uid in valid_ids]
        dropped = len(curation.selected_ids) - len(selected)
        if dropped:
            log.warning(f"Curation returned {dropped} unknown article IDs — dropped")
        return selected[:max_articles]

    # ── Stage 4: Reconstruct article content ──────────────────────────────────

    def _reconstruct_content(
        self,
        selected_ids: list[UUID],
        topics: list[SourceArticleDescriptor],
        source_map: dict[UUID, ChunkedSourceEmail],
    ) -> list[SelectedArticle]:
        topic_map = {t.article_id: t for t in topics}
        articles: list[SelectedArticle] = []

        for article_id in selected_ids:
            topic = topic_map.get(article_id)
            if topic is None or topic.article_email is None:
                log.warning(f"No topic found for article_id {article_id} — skipping")
                continue
            source = source_map.get(topic.article_email)
            if source is None:
                log.warning(
                    f"No source email for email_id {topic.article_email} — skipping"
                )
                continue

            chunk_map = {c.chunk_id: c.text for c in source.email_contents}
            chunks = [
                chunk_map[loc]
                for loc in topic.content_locations
                if loc in chunk_map
            ]
            articles.append(
                SelectedArticle(
                    article_id=article_id,
                    title=topic.title,
                    sender=source.sender,
                    sender_name=source.sender_name,
                    email_subject=source.email_subject,
                    content="\n\n".join(chunks),
                )
            )

        return articles

    # ── Stage 5: Transform to learning digest ─────────────────────────────────

    def _transform_articles(
        self,
        articles: list[SelectedArticle],
        llm_client: Any,
        prompts: PromptManager,
    ) -> TargetEmailContent:
        lang = self.config.language
        known_language = lang.known.name.title()
        target_language = lang.target.name.title()
        level = lang.level.name

        json_schema = json.dumps(TargetEmailContent.model_json_schema(), indent=2)
        language_extra = prompts.get("language_extra")
        tone_extra = prompts.get("tone_extra")
        article_structure_extra = prompts.get("article_structure_extra")

        articles_content = "\n\n---\n\n".join(
            f"## Article: {a.title}\nSource: {a.sender_name} ({a.email_subject})\n\n{a.content}"
            for a in articles
        )

        system_prompt = prompts.get(
            "system",
            known_language=known_language,
            target_language=target_language,
            level=level,
            language_extra=language_extra,
            tone_extra=tone_extra,
            article_structure_extra=article_structure_extra,
            json_schema=json_schema,
        )
        user_prompt = prompts.get("transform_user", articles_content=articles_content)
        fix_prompt = prompts.get("json_fix", json_schema=json_schema)

        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=MessageRole.USER, content=user_prompt),
        ]

        log.info(f"Transforming {len(articles)} articles via LLM")
        response = llm_client.complete(messages)
        return _parse_json_with_retry(
            raw=response.content,
            llm_client=llm_client,
            original_messages=messages,
            fix_prompt=fix_prompt,
            model_class=TargetEmailContent,
        )

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def build_digest(self, emails: list[Email]) -> DigestContent:
        """Run the 5-stage pipeline and render the result to email formats.

        Args:
            emails: Raw emails to transform into a learning digest.

        Returns:
            DigestContent with subject, plain-text body, and HTML body.

        Raises:
            ValueError: If any pipeline stage produces no usable output.
        """
        pipeline_cfg = self.config.pipeline
        prompts = PromptManager(overrides_path=self._prompts_path)
        llm_client = create_llm_client(self.config.llm)

        # Stage 1: chunk
        source_list = self._chunk_emails(emails)
        if not source_list:
            raise ValueError("No email content after chunking")
        source_map = {s.email_id: s for s in source_list}

        # Stage 2: topic extraction
        topics = self._extract_topics(source_list, llm_client, prompts)
        if not topics:
            raise ValueError("No topics extracted from emails")
        log.info(f"Extracted {len(topics)} topics from {len(source_list)} emails")

        # Stage 3: curation
        selected_ids = self._curate_articles(
            topics, pipeline_cfg.max_articles_in_final_email, llm_client, prompts
        )
        if not selected_ids:
            raise ValueError("No articles selected after curation")
        log.info(f"Curated {len(selected_ids)} articles for final digest")

        # Stage 4: reconstruct
        articles = self._reconstruct_content(selected_ids, topics, source_map)
        if not articles:
            raise ValueError("No article content reconstructed")

        # Stage 5: transform
        parsed = self._transform_articles(articles, llm_client, prompts)

        # Render
        tz = pytz.timezone(self.config.schedule.timezone)
        now = datetime.now(tz)
        date_str = now.strftime("%-d %B %Y")

        lang = self.config.language
        target_language = lang.target.name.title()
        title = f"Your {target_language} learning digest"
        subject = f"{title} — {date_str}"

        inline_images: list[InlineImage] = []
        logo_cid: str | None = None
        if _LOGO_PATH.exists():
            logo_cid = "logo"
            inline_images.append(
                InlineImage(cid=logo_cid, data=_LOGO_PATH.read_bytes())
            )

        return DigestContent(
            subject=subject,
            body_text=_render_text(parsed),
            body_html=_render_html(parsed, title, date_str, logo_cid),
            inline_images=inline_images,
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
                    inline_images=digest.inline_images or None,
                )
            log.info(f"Sent digest to {self.config.target_email.address}")
            return ProcessingResult(emails_processed=0, emails_sent=1, errors=[])
        except Exception as e:
            error_msg = f"Failed to send email: {e}"
            log.error(error_msg)
            return ProcessingResult(
                emails_processed=0, emails_sent=0, errors=[error_msg]
            )

    def process(self, emails: list[Email]) -> ProcessingResult:
        """Build and send a learning digest from a list of emails.

        Orchestrates build_digest() and send_target_email(). Use those methods
        directly when you need to intercept the digest before sending (e.g. dry-run).
        """
        if not emails:
            log.info("No emails to process")
            return ProcessingResult(0, 0, [])

        try:
            digest = self.build_digest(emails)
        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            log.error(error_msg)
            return ProcessingResult(
                emails_processed=len(emails), emails_sent=0, errors=[error_msg]
            )

        result = self.send_target_email(digest)
        result.emails_processed = len(emails)
        return result
