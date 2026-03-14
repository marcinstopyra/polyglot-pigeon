"""Split email bodies into UUID-keyed text chunks for LLM processing."""

import re
from html.parser import HTMLParser
from uuid import uuid4

from polyglot_pigeon.models.models import Email, SourceEmailContents

_CHUNK_BOUNDARY_TAGS = frozenset({"h1", "h2", "h3", "h4", "article", "section"})
_BLOCK_TAGS = frozenset({"p", "br", "div", "li"})
_SKIP_TAGS = frozenset({"script", "style", "figcaption"})
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


class _HTMLChunker(HTMLParser):
    """Splits HTML into text chunks at heading/section boundaries."""

    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []
        self._current: list[str] = []
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID_ELEMENTS and (tag in _SKIP_TAGS or self._is_hidden(attrs)):
            self._skip_stack.append(tag)
            return
        if self._skip_stack:
            return
        if tag in _CHUNK_BOUNDARY_TAGS:
            self._flush()
            self._current.append("\n")
        elif tag in _BLOCK_TAGS:
            self._current.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._skip_stack:
            self._current.append(data)

    def _flush(self) -> None:
        text = "".join(self._current).strip()
        if text:
            self._chunks.append(text)
        self._current = []

    def get_chunks(self) -> list[str]:
        self._flush()
        return self._chunks

    @staticmethod
    def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name == "style" and value:
                if re.search(r"display\s*:\s*none", value, re.IGNORECASE):
                    return True
        return False


def _chunk_html(html: str) -> list[str]:
    chunker = _HTMLChunker()
    chunker.feed(html)
    return chunker.get_chunks()


def _chunk_plain_text(text: str) -> list[str]:
    """Split plain text into chunks on double newlines and header-like lines."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        lines = para.split("\n")
        current: list[str] = []
        for line in lines:
            stripped = line.strip()
            is_header = bool(
                stripped
                and (
                    (stripped.replace(" ", "").isupper() and len(stripped) > 3)
                    or stripped.endswith(":")
                )
            )
            if is_header and current:
                chunk = "\n".join(current).strip()
                if chunk:
                    chunks.append(chunk)
                current = [line]
            else:
                current.append(line)
        if current:
            chunk = "\n".join(current).strip()
            if chunk:
                chunks.append(chunk)
    return chunks


def _extract_sender_name(sender: str) -> str:
    """Extract display name from 'Name <addr@example.com>' format."""
    if "<" in sender:
        name = sender[: sender.index("<")].strip().strip('"')
        return name if name else sender
    return sender


def chunk_email(email: Email, min_chars: int, max_chunks: int) -> SourceEmailContents:
    """Split an email body into UUID-keyed text chunks.

    Args:
        email: Raw email to chunk.
        min_chars: Drop chunks shorter than this (noise filter).
        max_chunks: Cap on number of chunks (takes first N).

    Returns:
        SourceEmailContents with UUID-keyed chunk dict.
    """
    if email.body_html:
        raw_chunks = _chunk_html(email.body_html)
    else:
        raw_chunks = _chunk_plain_text(email.body_text or "")

    chunks = [c for c in raw_chunks if len(c) >= min_chars]
    chunks = chunks[:max_chunks]

    email_contents = {uuid4(): chunk for chunk in chunks}

    return SourceEmailContents(
        email_id=uuid4(),
        sender=email.sender,
        sender_name=_extract_sender_name(email.sender),
        email_subject=email.subject,
        email_contents=email_contents,
    )
