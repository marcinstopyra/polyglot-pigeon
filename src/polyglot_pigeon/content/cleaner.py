"""Content cleaner that strips HTML and boilerplate from emails."""

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from polyglot_pigeon.models.models import Email

log = logging.getLogger(__name__)

_MAX_CONSECUTIVE_BLANK_LINES = 2
_BOILERPLATE_TAIL_THRESHOLD = 0.6

_BOILERPLATE_PATTERNS = [
    # --- DOTALL footer triggers (only fire in last 40% of text) ---
    re.compile(r"(?i)unsubscribe.*", re.DOTALL),
    re.compile(r"(?i)©\s*\d{4}.*", re.DOTALL),
    re.compile(r"(?i)you('re|\s+are)\s+receiving\s+this.*", re.DOTALL),
    re.compile(r"(?i)explore\s+(other\s+)?newsletters.*", re.DOTALL),
    re.compile(r"(?i)become\s+a\s+member.*", re.DOTALL),
    re.compile(r"(?i)(take|complete|fill\s+out)\s+(our|the)\s+survey.*", re.DOTALL),
    re.compile(
        r"(?i)follow\s+us\s+on\s+(twitter|x|facebook|instagram|linkedin).*", re.DOTALL
    ),
    # --- Line-level removals (applied everywhere) ---
    re.compile(r"(?i)view\s+(this\s+)?(email\s+)?in\s+(your\s+)?browser.*"),
    re.compile(r"(?i)manage\s+(your\s+)?preferences.*"),
    re.compile(r"(?im)^[^\n]*please\s+support\s+our\s+sponsors[^\n]*$"),
    re.compile(r"(?im)^[^\n]*in\s+partnership\s+with\b[^\n]*$"),
]

_TRACKING_URL_RE = re.compile(
    r"https?://\S*(?:list-manage\.com/track|sendgrid\.net/ls/click"
    r"|click\.convertkit-mail|mandrillapp\.com/track)\S*",
    re.IGNORECASE,
)

_INLINE_URL_RE = re.compile(r"\s*\(https?://[^\)\n]+\)")

_BARE_URL_RE = re.compile(r"^\s*https?://\S+\s*$", re.MULTILINE)

_UI_LABEL_RE = re.compile(
    r"^\s*(ADVERTISEMENT|DONATE|READ|WATCH|RELATED\s+COVERAGE\s*[➤►]?)\s*$",
    re.MULTILINE,
)

_INVISIBLE_CHARS_RE = re.compile(
    r"[\u034f\u00ad\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u2061\u2062\u2063]"
)

_HTML_DETECT_RE = re.compile(r"^\s*(?:<html|<!doctype\s+html|<!--)", re.IGNORECASE)


@dataclass
class CleanedEmail:
    """Cleaned email content with metadata."""

    subject: str
    sender: str
    body: str


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML parser that extracts visible text."""

    _SKIP_TAGS = frozenset({"script", "style", "figcaption"})
    # Void elements have no closing tag and cannot contain children, so pushing
    # them onto the skip stack would permanently lock it.
    _VOID_ELEMENTS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if (
            tag in self._SKIP_TAGS or self._is_hidden(attrs)
        ) and tag not in self._VOID_ELEMENTS:
            self._skip_stack.append(tag)
        elif not self._skip_stack:
            if tag == "img":
                pass  # Skip images entirely
            elif tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
                self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._skip_stack:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)

    @staticmethod
    def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name == "style" and value:
                if re.search(r"display\s*:\s*none", value, re.IGNORECASE):
                    return True
        return False


class ContentCleaner:
    """Cleans email content for LLM processing.

    Prefers body_text when available, unless it looks like raw HTML,
    in which case falls back to stripping HTML from body_html.
    Removes common newsletter boilerplate.
    """

    def clean(self, emails: list[Email]) -> list[CleanedEmail]:
        """Clean a list of emails, returning cleaned content with metadata."""
        results = []
        for email in emails:
            body = self._extract_text(email)
            body = self._remove_boilerplate(body)
            body = self._strip_tracking_urls(body)
            body = self._strip_inline_urls(body)
            body = self._strip_bare_urls(body)
            body = self._strip_ui_labels(body)
            body = self._deduplicate_lines(body)
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
                log.warning(f"Email '{email.subject}' had no content after cleaning")

        return results

    def _extract_text(self, email: Email) -> str:
        if email.body_text and not _HTML_DETECT_RE.match(email.body_text):
            return email.body_text
        if email.body_html:
            return self._strip_html(email.body_html)
        if email.body_text:
            return self._strip_html(email.body_text)
        return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        return extractor.get_text()

    @staticmethod
    def _remove_boilerplate(text: str) -> str:
        tail_start = int(len(text) * _BOILERPLATE_TAIL_THRESHOLD)
        for pattern in _BOILERPLATE_PATTERNS:
            if pattern.flags & re.DOTALL:
                m = pattern.search(text)
                if m and m.start() >= tail_start:
                    text = text[: m.start()]
            else:
                text = pattern.sub("", text)
        return text

    @staticmethod
    def _strip_tracking_urls(text: str) -> str:
        return _TRACKING_URL_RE.sub("", text)

    @staticmethod
    def _strip_inline_urls(text: str) -> str:
        return _INLINE_URL_RE.sub("", text)

    @staticmethod
    def _strip_bare_urls(text: str) -> str:
        return _BARE_URL_RE.sub("", text)

    @staticmethod
    def _strip_ui_labels(text: str) -> str:
        return _UI_LABEL_RE.sub("", text)

    @staticmethod
    def _deduplicate_lines(text: str) -> str:
        lines = text.split("\n")
        result = []
        prev_stripped = None
        for line in lines:
            stripped = line.strip()
            if stripped and stripped == prev_stripped:
                continue
            result.append(line)
            if stripped:
                prev_stripped = stripped
        return "\n".join(result)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        text = _INVISIBLE_CHARS_RE.sub("", text)
        text = re.sub(r"\u00a0", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        # Enforce max 2 consecutive blank lines; treat whitespace-only lines as blank
        lines = text.split("\n")
        result: list[str] = []
        blank_run = 0
        for line in lines:
            if line.strip():
                blank_run = 0
                result.append(line)
            else:
                blank_run += 1
                if blank_run <= _MAX_CONSECUTIVE_BLANK_LINES:
                    result.append("")
        return "\n".join(result)
