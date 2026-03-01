"""Tests for pipeline helpers."""

import pytest

from polyglot_pigeon.scheduler.pipeline import markdown_to_email_html


class TestMarkdownToEmailHtml:
    """Tests for the markdown_to_email_html conversion helper."""

    def test_returns_valid_html_document(self):
        result = markdown_to_email_html("Hello")

        assert result.startswith("<!DOCTYPE html>")
        assert "<html>" in result
        assert "</html>" in result
        assert "<body>" in result
        assert "</body>" in result

    def test_includes_style_block(self):
        result = markdown_to_email_html("Hello")

        assert "<style>" in result
        assert "</style>" in result

    def test_includes_charset_meta(self):
        result = markdown_to_email_html("Hello")

        assert "charset='utf-8'" in result

    def test_headings_converted(self):
        result = markdown_to_email_html("# Title\n\n## Section")

        assert "<h1>Title</h1>" in result
        assert "<h2>Section</h2>" in result

    def test_bold_converted(self):
        result = markdown_to_email_html("**word**: definition")

        assert "<strong>word</strong>" in result

    def test_paragraph_converted(self):
        result = markdown_to_email_html("A simple paragraph.")

        assert "<p>A simple paragraph.</p>" in result

    def test_hr_converted(self):
        result = markdown_to_email_html("above\n\n---\n\nbelow")

        assert "<hr" in result

    def test_hr_normalisation_handles_extra_blank_lines(self):
        """Messy whitespace around --- should still produce a single <hr>."""
        messy = "above\n\n\n\n---\n\n\n\nbelow"
        clean = "above\n\n---\n\nbelow"

        assert markdown_to_email_html(messy) == markdown_to_email_html(clean)

    def test_table_converted(self):
        md = "| Word | Meaning |\n|------|--------|\n| chat | cat |"
        result = markdown_to_email_html(md)

        assert "<table>" in result
        assert "<th>" in result
        assert "<td>" in result

    def test_empty_string(self):
        result = markdown_to_email_html("")

        assert "<!DOCTYPE html>" in result
        assert "<body></body>" in result

    def test_full_digest_structure(self):
        """Smoke-test a realistic digest body."""
        body = (
            "Great news today.\n\n"
            "## Articles:\n\n"
            "### Article 1\n\n"
            "Some text in the target language.\n\n"
            "---\n\n"
            "**Wort**: word\n\n"
            "### Article 2\n\n"
            "More content here.\n\n"
            "---\n\n"
            "**Satz**: sentence\n"
        )
        result = markdown_to_email_html(body)

        assert "<h2>Articles:</h2>" in result
        assert "<h3>Article 1</h3>" in result
        assert "<h3>Article 2</h3>" in result
        assert result.count("<hr") == 2
