"""Tests for pipeline helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from polyglot_pigeon.llm.models import LLMMessage, LLMResponse, MessageRole
from polyglot_pigeon.models.models import TargetArticle, TargetEmailContent
from polyglot_pigeon.scheduler.pipeline import (
    EmailProcessingPipeline,
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

_TITLE = "Your German learning digest"
_DATE = "2 March 2026"


def _render(*args, title=_TITLE, date=_DATE, logo_cid=None, **kwargs):
    """Shorthand that supplies default title/date/logo_cid to _render_html."""
    return _render_html(_digest(*args, **kwargs), title, date, logo_cid)


class TestRenderHtml:
    def test_returns_valid_html_structure(self):
        result = _render()

        assert result.startswith("<!DOCTYPE html>")
        assert "<html>" in result
        assert "</html>" in result
        assert "<body>" in result
        assert "</body>" in result

    def test_includes_style_block(self):
        assert "<style>" in _render()

    def test_includes_charset_meta(self):
        assert 'charset="utf-8"' in _render()

    def test_introduction_rendered(self):
        assert "My intro." in _render(introduction="My intro.")

    def test_article_title_in_h3(self):
        assert "<h3>Big News</h3>" in _render(articles=[_article(title="Big News")])

    def test_source_and_date_in_em(self):
        result = _render(articles=[_article(source="BBC", date="2024-06-01")])

        assert "<em>BBC" in result
        assert "2024-06-01" in result

    def test_glossary_entries_as_paragraphs(self):
        result = _render(articles=[_article(glossary={"chat": "cat", "chien": "dog"})])

        assert "<strong>chat</strong>: cat" in result
        assert "<strong>chien</strong>: dog" in result

    def test_single_article_no_leading_hr(self):
        assert "<hr>" not in _render(articles=[_article(glossary={})])

    def test_single_article_with_glossary_has_one_hr(self):
        assert _render(articles=[_article()]).count("<hr>") == 1

    def test_two_articles_hr_between_them(self):
        result = _render(articles=[_article(glossary={}), _article(glossary={})])

        # one <hr> between articles, none inside (empty glossaries)
        assert result.count("<hr>") == 1

    def test_two_articles_with_glossaries_hr_count(self):
        result = _render(articles=[_article(), _article()])

        # article separator (1) + two content/glossary separators (2) = 3
        assert result.count("<hr>") == 3

    def test_empty_glossary_no_extra_hr(self):
        assert _render(articles=[_article(glossary={})]).count("<hr>") == 0

    def test_header_contains_title(self):
        result = _render(title="Your French digest")

        assert "Your French digest" in result
        assert 'class="header"' in result

    def test_header_contains_date(self):
        assert "15 January 2025" in _render(date="15 January 2025")

    def test_logo_cid_used_in_img_src(self):
        result = _render(logo_cid="logo")

        assert 'src="cid:logo"' in result

    def test_no_img_when_logo_cid_is_none(self):
        assert "<img" not in _render(logo_cid=None)


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


# ── EmailProcessingPipeline — prompts_path ────────────────────────────────────


def _mock_config():
    config = MagicMock()
    config.language.known.name = "english"
    config.language.target.name = "german"
    config.language.level.name = "B1"
    config.schedule.timezone = "UTC"
    return config


class TestEmailProcessingPipelinePromptsPath:
    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_default_prompts_path_is_none(self, mock_get_config):
        mock_get_config.return_value = _mock_config()

        pipeline = EmailProcessingPipeline()

        assert pipeline._prompts_path is None

    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_custom_prompts_path_stored(self, mock_get_config, tmp_path):
        mock_get_config.return_value = _mock_config()
        prompts_file = tmp_path / "prompts.yaml"

        pipeline = EmailProcessingPipeline(prompts_path=prompts_file)

        assert pipeline._prompts_path == prompts_file

    @patch("polyglot_pigeon.scheduler.pipeline.PromptManager")
    @patch("polyglot_pigeon.scheduler.pipeline.create_llm_client")
    @patch("polyglot_pigeon.scheduler.pipeline.ContentCleaner")
    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_prompts_path_forwarded_to_prompt_manager(
        self, mock_get_config, mock_cleaner_cls, mock_llm_factory, mock_pm_cls, tmp_path
    ):
        mock_get_config.return_value = _mock_config()
        mock_cleaner_cls.return_value.clean.return_value = [
            MagicMock(subject="News", sender="test@example.com", body="Some content.")
        ]
        mock_pm_cls.return_value.get.return_value = "prompt text"
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(
            content=_digest().model_dump_json(), model="mock", stop_reason="end_turn"
        )
        mock_llm_factory.return_value = mock_llm

        prompts_file = tmp_path / "prompts.yaml"
        pipeline = EmailProcessingPipeline(prompts_path=prompts_file)
        pipeline.build_digest([MagicMock()])

        mock_pm_cls.assert_called_once_with(overrides_path=prompts_file)

    @patch("polyglot_pigeon.scheduler.pipeline.PromptManager")
    @patch("polyglot_pigeon.scheduler.pipeline.create_llm_client")
    @patch("polyglot_pigeon.scheduler.pipeline.ContentCleaner")
    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_none_prompts_path_forwarded_to_prompt_manager(
        self, mock_get_config, mock_cleaner_cls, mock_llm_factory, mock_pm_cls
    ):
        mock_get_config.return_value = _mock_config()
        mock_cleaner_cls.return_value.clean.return_value = [
            MagicMock(subject="News", sender="test@example.com", body="Some content.")
        ]
        mock_pm_cls.return_value.get.return_value = "prompt text"
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(
            content=_digest().model_dump_json(), model="mock", stop_reason="end_turn"
        )
        mock_llm_factory.return_value = mock_llm

        pipeline = EmailProcessingPipeline(prompts_path=None)
        pipeline.build_digest([MagicMock()])

        mock_pm_cls.assert_called_once_with(overrides_path=None)
