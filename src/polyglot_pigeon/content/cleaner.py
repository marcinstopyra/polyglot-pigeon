"""Content cleaner that strips HTML and boilerplate from emails."""

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from polyglot_pigeon.models.models import Email

logger = logging.getLogger(__name__)

_BOILERPLATE_PATTERNS = [
    re.compile(r"(?i)unsubscribe.*", re.DOTALL),
    re.compile(r"(?i)view\s+(this\s+)?(email\s+)?in\s+(your\s+)?browser.*"),
    re.compile(r"(?i)manage\s+(your\s+)?preferences.*"),
    re.compile(r"(?i)©\s*\d{4}.*", re.DOTALL),
    re.compile(r"(?i)you('re|\s+are)\s+receiving\s+this.*", re.DOTALL),
]


@dataclass
class CleanedEmail:
    """Cleaned email content with metadata."""

    subject: str
    sender: str
    body: str


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML parser that extracts visible text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    _SKIP_TAGS = {"script", "style", "figcaption"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip = True
        elif tag == "img":
            pass  # Skip images entirely (alt text is not useful without the image)
        elif tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


class ContentCleaner:
    """Cleans email content for LLM processing.

    Prefers body_text when available. Falls back to stripping HTML
    from body_html. Removes common newsletter boilerplate.
    """

    def clean(self, emails: list[Email]) -> list[CleanedEmail]:
        """Clean a list of emails, returning cleaned content with metadata."""
        results = []
        for email in emails:
            body = self._extract_text(email)
            body = self._remove_boilerplate(body)
            body = self._normalize_whitespace(body)

            if body.strip():
                results.append(
                    CleanedEmail(
                        subject=email.subject,
                        sender=email.sender,
                        body=body.strip(),
                    )
                )
            else:
                logger.warning(f"Email '{email.subject}' had no content after cleaning")

        return results

    def _extract_text(self, email: Email) -> str:
        if email.body_text:
            return email.body_text
        if email.body_html:
            return self._strip_html(email.body_html)
        return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        return extractor.get_text()

    @staticmethod
    def _remove_boilerplate(text: str) -> str:
        for pattern in _BOILERPLATE_PATTERNS:
            text = pattern.sub("", text)
        return text

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text
