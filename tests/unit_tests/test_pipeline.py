"""Tests for pipeline helpers."""

from unittest.mock import MagicMock

import pytest

from polyglot_pigeon.llm.models import LLMMessage, LLMResponse, MessageRole
from polyglot_pigeon.models.models import TargetArticle, TargetEmailContent
from polyglot_pigeon.scheduler.pipeline import (
    _parse_json_with_retry,
    _render_html,
    _render_text,
    _strip_json_fences,
)

# ── fixtures / helpers ────────────────────────────────────────────────────────


def _article(**kwargs) -> TargetArticle:
    defaults = dict(
        title="Test Title",
        source="Test Source",
        date="2024-01-01",
        content="Some content.",
        glossary={"word": "translation"},
    )
    defaults.update(kwargs)
    return TargetArticle(**defaults)


def _digest(**kwargs) -> TargetEmailContent:
    defaults = dict(
        introduction="Today's introduction.",
        articles=[_article()],
    )
    defaults.update(kwargs)
    return TargetEmailContent(**defaults)


def _mock_llm(responses: list[str]) -> MagicMock:
    client = MagicMock()
    client.complete.side_effect = [
        LLMResponse(content=r, model="mock", stop_reason="end_turn")
        for r in responses
    ]
    return client


_MESSAGES = [LLMMessage(role=MessageRole.USER, content="transform this")]
_FIX_PROMPT = "Fix the JSON."


# ── _strip_json_fences ────────────────────────────────────────────────────────


class TestStripJsonFences:
    def test_plain_json_unchanged(self):
        raw = '{"key": "value"}'
        assert _strip_json_fences(raw) == raw

    def test_strips_json_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_strips_plain_fences(self):
        raw = '```\n{"key": "value"}\n```'
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_strips_surrounding_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_strips_whitespace_inside_fences(self):
        raw = '```json\n  {"key": "value"}  \n```'
        assert _strip_json_fences(raw) == '{"key": "value"}'


# ── _render_html ──────────────────────────────────────────────────────────────


class TestRenderHtml:
    def test_returns_valid_html_structure(self):
        result = _render_html(_digest())

        assert result.startswith("<!DOCTYPE html>")
        assert "<html>" in result
        assert "</html>" in result
        assert "<body>" in result
        assert "</body>" in result

    def test_includes_style_block(self):
        result = _render_html(_digest())

        assert "<style>" in result

    def test_includes_charset_meta(self):
        result = _render_html(_digest())

        assert "charset='utf-8'" in result

    def test_introduction_rendered(self):
        result = _render_html(_digest(introduction="My intro."))

        assert "My intro." in result

    def test_article_title_in_h3(self):
        result = _render_html(_digest(articles=[_article(title="Big News")]))

        assert "<h3>Big News</h3>" in result

    def test_source_and_date_in_em(self):
        result = _render_html(_digest(articles=[_article(source="BBC", date="2024-06-01")]))

        assert "<em>BBC" in result
        assert "2024-06-01" in result

    def test_glossary_entries_as_paragraphs(self):
        a = _article(glossary={"chat": "cat", "chien": "dog"})
        result = _render_html(_digest(articles=[a]))

        assert "<strong>chat</strong>: cat" in result
        assert "<strong>chien</strong>: dog" in result

    def test_single_article_no_leading_hr(self):
        result = _render_html(_digest(articles=[_article(glossary={})]))

        assert "<hr>" not in result

    def test_single_article_with_glossary_has_one_hr(self):
        result = _render_html(_digest(articles=[_article()]))

        assert result.count("<hr>") == 1

    def test_two_articles_hr_between_them(self):
        result = _render_html(_digest(articles=[
            _article(glossary={}),
            _article(glossary={}),
        ]))

        # one <hr> between articles, none inside (empty glossaries)
        assert result.count("<hr>") == 1

    def test_two_articles_with_glossaries_hr_count(self):
        result = _render_html(_digest(articles=[_article(), _article()]))

        # article separator (1) + two content/glossary separators (2) = 3
        assert result.count("<hr>") == 3

    def test_empty_glossary_no_extra_hr(self):
        result = _render_html(_digest(articles=[_article(glossary={})]))

        assert result.count("<hr>") == 0


# ── _render_text ──────────────────────────────────────────────────────────────


class TestRenderText:
    def test_introduction_present(self):
        result = _render_text(_digest(introduction="Hello world."))

        assert "Hello world." in result

    def test_article_title_present(self):
        result = _render_text(_digest(articles=[_article(title="Big News")]))

        assert "## Big News" in result

    def test_source_and_date_present(self):
        result = _render_text(_digest(articles=[_article(source="BBC", date="2024-06-01")]))

        assert "BBC" in result
        assert "2024-06-01" in result

    def test_glossary_entries_each_on_own_line(self):
        a = _article(glossary={"chat": "cat", "chien": "dog"})
        lines = _render_text(_digest(articles=[a])).splitlines()

        assert any("**chat**: cat" in line for line in lines)
        assert any("**chien**: dog" in line for line in lines)
        # they must be on different lines
        chat_line = next(i for i, l in enumerate(lines) if "**chat**: cat" in l)
        chien_line = next(i for i, l in enumerate(lines) if "**chien**: dog" in l)
        assert chat_line != chien_line

    def test_single_article_no_leading_separator(self):
        result = _render_text(_digest(articles=[_article()]))

        # first non-empty line after intro should be the article heading, not ---
        lines = [l for l in result.splitlines() if l.strip()]
        intro_idx = next(i for i, l in enumerate(lines) if "introduction" in l.lower())
        next_meaningful = lines[intro_idx + 1]
        assert next_meaningful != "---"

    def test_two_articles_separated_by_hr(self):
        result = _render_text(_digest(articles=[_article(), _article()]))

        assert result.count("---") >= 1


# ── _parse_json_with_retry ────────────────────────────────────────────────────


class TestParseJsonWithRetry:
    def test_valid_json_parsed_directly(self):
        raw = _digest().model_dump_json()
        result = _parse_json_with_retry(raw, _mock_llm([]), _MESSAGES, _FIX_PROMPT)

        assert isinstance(result, TargetEmailContent)
        assert result.introduction == "Today's introduction."

    def test_fenced_json_parsed_after_strip(self):
        raw = f"```json\n{_digest().model_dump_json()}\n```"
        result = _parse_json_with_retry(raw, _mock_llm([]), _MESSAGES, _FIX_PROMPT)

        assert isinstance(result, TargetEmailContent)

    def test_no_llm_calls_on_first_success(self):
        client = _mock_llm([])
        _parse_json_with_retry(_digest().model_dump_json(), client, _MESSAGES, _FIX_PROMPT)

        client.complete.assert_not_called()

    def test_invalid_json_retries_and_succeeds(self):
        valid = _digest().model_dump_json()
        client = _mock_llm(["not json at all", valid])

        result = _parse_json_with_retry("bad input", client, _MESSAGES, _FIX_PROMPT, max_retries=3)

        assert isinstance(result, TargetEmailContent)
        assert client.complete.call_count == 2

    def test_fix_prompt_sent_on_retry(self):
        valid = _digest().model_dump_json()
        client = _mock_llm([valid])

        _parse_json_with_retry("bad input", client, _MESSAGES, _FIX_PROMPT, max_retries=3)

        call_messages = client.complete.call_args[0][0]
        assert call_messages[-1].content == _FIX_PROMPT

    def test_exhausted_retries_raises(self):
        client = _mock_llm(["bad"] * 5)

        with pytest.raises(ValueError, match="retries"):
            _parse_json_with_retry("bad", client, _MESSAGES, _FIX_PROMPT, max_retries=3)

    def test_exhausted_retries_calls_llm_max_retries_times(self):
        client = _mock_llm(["bad"] * 5)

        with pytest.raises(ValueError):
            _parse_json_with_retry("bad", client, _MESSAGES, _FIX_PROMPT, max_retries=3)

        assert client.complete.call_count == 3

    def test_succeeds_on_last_retry(self):
        valid = _digest().model_dump_json()
        client = _mock_llm(["bad", "bad", valid])

        result = _parse_json_with_retry("bad", client, _MESSAGES, _FIX_PROMPT, max_retries=3)

        assert isinstance(result, TargetEmailContent)
        assert client.complete.call_count == 3
