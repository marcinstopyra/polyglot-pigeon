"""Tests for the email chunker (content/chunker.py)."""

from datetime import datetime
from uuid import UUID

from polyglot_pigeon.content.chunker import (
    _chunk_html,
    _chunk_plain_text,
    _extract_sender_name,
    chunk_email,
)
from polyglot_pigeon.models.models import Email, ChunkedSourceEmail

# ── helpers ───────────────────────────────────────────────────────────────────


def _email(**kwargs) -> Email:
    defaults = dict(
        uid="1",
        subject="Test Newsletter",
        sender="Test Sender <test@example.com>",
        date=datetime(2024, 1, 1),
        body_text="Default body text.",
        body_html=None,
    )
    defaults.update(kwargs)
    return Email(**defaults)


# ── _extract_sender_name ──────────────────────────────────────────────────────


class TestExtractSenderName:
    def test_name_and_address(self):
        assert _extract_sender_name("John Doe <john@example.com>") == "John Doe"

    def test_quoted_name_and_address(self):
        assert (
            _extract_sender_name('"The Newsletter" <news@example.com>')
            == "The Newsletter"
        )

    def test_address_only(self):
        assert _extract_sender_name("john@example.com") == "john@example.com"

    def test_empty_name_falls_back_to_full_string(self):
        assert _extract_sender_name("<john@example.com>") == "<john@example.com>"


# ── _chunk_html ───────────────────────────────────────────────────────────────


class TestChunkHtml:
    def test_single_paragraph(self):
        html = "<p>Hello world</p>"
        chunks = _chunk_html(html)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]

    def test_heading_starts_new_chunk(self):
        html = "<p>Intro text.</p><h2>Section</h2><p>Body text.</p>"
        chunks = _chunk_html(html)
        # h2 should trigger a boundary — we get the intro chunk and the section chunk
        assert len(chunks) >= 2
        assert any("Intro text." in c for c in chunks)
        assert any("Section" in c for c in chunks)

    def test_multiple_headings_produce_multiple_chunks(self):
        html = (
            "<h1>Topic A</h1><p>Content A.</p>"
            "<h2>Topic B</h2><p>Content B.</p>"
            "<h3>Topic C</h3><p>Content C.</p>"
        )
        chunks = _chunk_html(html)
        assert len(chunks) >= 3

    def test_scripts_excluded(self):
        html = "<p>Visible</p><script>alert('hidden')</script><p>Also visible</p>"
        chunks = _chunk_html(html)
        combined = " ".join(chunks)
        assert "hidden" not in combined
        assert "Visible" in combined

    def test_hidden_div_excluded(self):
        html = '<p>Shown</p><div style="display: none">Hidden</div><p>Also shown</p>'
        chunks = _chunk_html(html)
        combined = " ".join(chunks)
        assert "Hidden" not in combined
        assert "Shown" in combined

    def test_empty_html_returns_no_chunks(self):
        assert _chunk_html("") == []
        assert _chunk_html("<div></div>") == []

    def test_article_tag_starts_new_chunk(self):
        html = "<p>Preamble</p><article><p>Article body.</p></article>"
        chunks = _chunk_html(html)
        assert len(chunks) >= 2


# ── _chunk_plain_text ─────────────────────────────────────────────────────────


class TestChunkPlainText:
    def test_double_newline_splits(self):
        text = "First paragraph.\n\nSecond paragraph."
        chunks = _chunk_plain_text(text)
        assert len(chunks) == 2
        assert chunks[0] == "First paragraph."
        assert chunks[1] == "Second paragraph."

    def test_allcaps_header_starts_new_chunk(self):
        text = "Intro line.\nNEWS\nBody of news."
        chunks = _chunk_plain_text(text)
        assert any("Intro line." in c for c in chunks)
        assert any("NEWS" in c for c in chunks)

    def test_colon_line_starts_new_chunk(self):
        text = "Before.\nSection Title:\nAfter."
        chunks = _chunk_plain_text(text)
        # "Section Title:" line should start a new chunk
        assert len(chunks) >= 2

    def test_empty_string_returns_empty(self):
        assert _chunk_plain_text("") == []

    def test_multiple_blank_lines_treated_as_one_boundary(self):
        text = "A.\n\n\n\nB."
        chunks = _chunk_plain_text(text)
        assert len(chunks) == 2


# ── chunk_email ───────────────────────────────────────────────────────────────


class TestChunkEmail:
    def test_returns_source_email_contents(self):
        email = _email(body_text="Hello.\n\nWorld.")
        result = chunk_email(email, min_chars=1, max_chunks=100)
        assert isinstance(result, ChunkedSourceEmail)

    def test_email_fields_populated(self):
        email = _email(
            subject="My Newsletter",
            sender="Alice <alice@example.com>",
            body_text="Some content.",
        )
        result = chunk_email(email, min_chars=1, max_chunks=100)
        assert result.email_subject == "My Newsletter"
        assert result.sender == "Alice <alice@example.com>"
        assert result.sender_name == "Alice"

    def test_each_chunk_has_uuid_key(self):
        email = _email(body_text="Chunk one.\n\nChunk two.\n\nChunk three.")
        result = chunk_email(email, min_chars=1, max_chunks=100)
        for chunk in result.email_contents:
            assert isinstance(chunk.chunk_id, UUID)

    def test_min_chars_filters_short_chunks(self):
        email = _email(body_text="Hi.\n\nThis is a longer paragraph with real content.")
        result = chunk_email(email, min_chars=10, max_chunks=100)
        for chunk in result.email_contents:
            assert len(chunk.text) >= 10

    def test_max_chunks_cap(self):
        paragraphs = "\n\n".join(
            f"Paragraph number {i} with enough text." for i in range(20)
        )
        email = _email(body_text=paragraphs)
        result = chunk_email(email, min_chars=1, max_chunks=5)
        assert len(result.email_contents) <= 5

    def test_html_preferred_over_plain_text(self):
        email = _email(
            body_html="<h1>From HTML</h1><p>HTML body.</p>",
            body_text="Plain text body.",
        )
        result = chunk_email(email, min_chars=1, max_chunks=100)
        combined = " ".join(c.text for c in result.email_contents)
        assert "From HTML" in combined
        assert "Plain text body." not in combined

    def test_plain_text_fallback_when_no_html(self):
        email = _email(
            body_html=None, body_text="Plain text only.\n\nSecond paragraph."
        )
        result = chunk_email(email, min_chars=1, max_chunks=100)
        combined = " ".join(c.text for c in result.email_contents)
        assert "Plain text only." in combined

    def test_no_content_returns_empty_dict(self):
        email = _email(body_html=None, body_text="")
        result = chunk_email(email, min_chars=1, max_chunks=100)
        assert result.email_contents == []

    def test_unique_email_ids_per_call(self):
        email = _email(body_text="Content.")
        result1 = chunk_email(email, min_chars=1, max_chunks=100)
        result2 = chunk_email(email, min_chars=1, max_chunks=100)
        assert result1.email_id != result2.email_id
