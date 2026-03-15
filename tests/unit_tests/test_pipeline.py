"""Tests for pipeline helpers and stage methods."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from polyglot_pigeon.llm.models import LLMMessage, LLMResponse, MessageRole
from polyglot_pigeon.models.models import (
    SourceArticleDescriptor,
    TopicExtractionResponse,
    CurationResponse,
    EmailChunk,
    SelectedArticle,
    ChunkedSourceEmail,
    TargetArticle,
    TargetEmailContent,
)
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
        LLMResponse(content=r, model="mock", stop_reason="end_turn") for r in responses
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
        result = _render_text(
            _digest(articles=[_article(source="BBC", date="2024-06-01")])
        )

        assert "BBC" in result
        assert "2024-06-01" in result

    def test_glossary_entries_each_on_own_line(self):
        a = _article(glossary={"chat": "cat", "chien": "dog"})
        lines = _render_text(_digest(articles=[a])).splitlines()

        assert any("**chat**: cat" in line for line in lines)
        assert any("**chien**: dog" in line for line in lines)
        # they must be on different lines
        chat_line = next(i for i, line in enumerate(lines) if "**chat**: cat" in line)
        chien_line = next(i for i, line in enumerate(lines) if "**chien**: dog" in line)
        assert chat_line != chien_line

    def test_single_article_no_leading_separator(self):
        result = _render_text(_digest(articles=[_article()]))

        # first non-empty line after intro should be the article heading, not ---
        lines = [line for line in result.splitlines() if line.strip()]
        intro_idx = next(
            i for i, line in enumerate(lines) if "introduction" in line.lower()
        )
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
        _parse_json_with_retry(
            _digest().model_dump_json(), client, _MESSAGES, _FIX_PROMPT
        )

        client.complete.assert_not_called()

    def test_invalid_json_retries_and_succeeds(self):
        valid = _digest().model_dump_json()
        client = _mock_llm(["not json at all", valid])

        result = _parse_json_with_retry(
            "bad input", client, _MESSAGES, _FIX_PROMPT, max_retries=3
        )

        assert isinstance(result, TargetEmailContent)
        assert client.complete.call_count == 2

    def test_fix_prompt_sent_on_retry(self):
        valid = _digest().model_dump_json()
        client = _mock_llm([valid])

        _parse_json_with_retry(
            "bad input", client, _MESSAGES, _FIX_PROMPT, max_retries=3
        )

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

        result = _parse_json_with_retry(
            "bad", client, _MESSAGES, _FIX_PROMPT, max_retries=3
        )

        assert isinstance(result, TargetEmailContent)
        assert client.complete.call_count == 3

    def test_custom_model_class_parses_correctly(self):
        """model_class param allows parsing into models other than TargetEmailContent."""
        curation = CurationResponse(selected_ids=[uuid4(), uuid4()])
        raw = curation.model_dump_json()

        result = _parse_json_with_retry(
            raw, _mock_llm([]), _MESSAGES, _FIX_PROMPT, model_class=CurationResponse
        )

        assert isinstance(result, CurationResponse)
        assert len(result.selected_ids) == 2


# ── EmailProcessingPipeline — prompts_path ────────────────────────────────────


def _mock_config():
    config = MagicMock()
    config.language.known.name = "english"
    config.language.target.name = "german"
    config.language.level.name = "B1"
    config.schedule.timezone = "UTC"
    config.pipeline.max_articles_in_final_email = 7
    config.pipeline.min_chunk_chars = 80
    config.pipeline.max_chunks_per_email = 60
    config.pipeline.show_cost_in_footer = False
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
    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_prompts_path_forwarded_to_prompt_manager(
        self, mock_get_config, mock_llm_factory, mock_pm_cls, tmp_path
    ):
        mock_get_config.return_value = _mock_config()
        mock_pm_cls.return_value.get.return_value = "prompt text"

        prompts_file = tmp_path / "prompts.yaml"
        pipeline = EmailProcessingPipeline(prompts_path=prompts_file)

        # Mock all stage methods so build_digest doesn't make real LLM calls
        source = _make_source()
        article_id = uuid4()
        topic = MagicMock()
        topic.article_id = article_id
        pipeline._chunk_emails = MagicMock(return_value=[source])
        pipeline._extract_topics = MagicMock(return_value=[topic])
        pipeline._curate_articles = MagicMock(return_value=[article_id])
        pipeline._reconstruct_content = MagicMock(return_value=[MagicMock()])
        pipeline._transform_articles = MagicMock(return_value=_digest())

        pipeline.build_digest([MagicMock()])

        mock_pm_cls.assert_called_once_with(overrides_path=prompts_file)

    @patch("polyglot_pigeon.scheduler.pipeline.PromptManager")
    @patch("polyglot_pigeon.scheduler.pipeline.create_llm_client")
    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_none_prompts_path_forwarded_to_prompt_manager(
        self, mock_get_config, mock_llm_factory, mock_pm_cls
    ):
        mock_get_config.return_value = _mock_config()
        mock_pm_cls.return_value.get.return_value = "prompt text"

        pipeline = EmailProcessingPipeline(prompts_path=None)

        source = _make_source()
        article_id = uuid4()
        topic = MagicMock()
        topic.article_id = article_id
        pipeline._chunk_emails = MagicMock(return_value=[source])
        pipeline._extract_topics = MagicMock(return_value=[topic])
        pipeline._curate_articles = MagicMock(return_value=[article_id])
        pipeline._reconstruct_content = MagicMock(return_value=[MagicMock()])
        pipeline._transform_articles = MagicMock(return_value=_digest())

        pipeline.build_digest([MagicMock()])

        mock_pm_cls.assert_called_once_with(overrides_path=None)


# ── _extract_topics ───────────────────────────────────────────────────────────


def _make_source(chunks: list[EmailChunk] | None = None) -> ChunkedSourceEmail:
    return ChunkedSourceEmail(
        email_id=uuid4(),
        sender="Test Sender <test@example.com>",
        sender_name="Test Sender",
        email_subject="Weekly Digest",
        email_contents=chunks or [EmailChunk(chunk_id=uuid4(), text="Some article content here.")],
    )


def _make_topic_list_json(source: ChunkedSourceEmail, extra_uuid: bool = False) -> str:
    chunk_ids = [c.chunk_id for c in source.email_contents]
    locations = [str(chunk_ids[0])]
    if extra_uuid:
        locations.append(str(uuid4()))  # invalid UUID not in source
    topic = SourceArticleDescriptor(
        title="Test Article",
        content_locations=[chunk_ids[0]] + ([uuid4()] if extra_uuid else []),
        tags=["tech"],
    )
    # Manually build JSON to match what the LLM would return
    topic_list = TopicExtractionResponse(articles=[topic])
    return topic_list.model_dump_json()


class TestExtractTopics:
    def _make_pipeline(self) -> EmailProcessingPipeline:
        with patch("polyglot_pigeon.scheduler.pipeline.get_config") as mock_cfg:
            mock_cfg.return_value = _mock_config()
            return EmailProcessingPipeline()

    def test_valid_response_returns_topics(self):
        pipeline = self._make_pipeline()
        source = _make_source()
        topic_json = _make_topic_list_json(source)
        llm_client = _mock_llm([topic_json])

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        topics = pipeline._extract_topics([source], llm_client, prompts)

        assert len(topics) == 1
        assert topics[0].title == "Test Article"
        assert topics[0].article_email == source.email_id

    def test_invalid_uuids_are_dropped(self):
        """LLM returns a UUID not in email_contents — it should be silently dropped."""
        pipeline = self._make_pipeline()
        source = _make_source()
        chunk_id = source.email_contents[0].chunk_id
        rogue_id = uuid4()

        topic = SourceArticleDescriptor(
            title="Mixed",
            content_locations=[chunk_id, rogue_id],
            tags=["news"],
        )
        topic_list = TopicExtractionResponse(articles=[topic])
        llm_client = _mock_llm([topic_list.model_dump_json()])

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        topics = pipeline._extract_topics([source], llm_client, prompts)

        assert len(topics) == 1
        assert rogue_id not in topics[0].content_locations
        assert chunk_id in topics[0].content_locations

    def test_topic_with_all_invalid_uuids_skipped(self):
        """If all content_locations are invalid, the topic is dropped entirely."""
        pipeline = self._make_pipeline()
        source = _make_source()

        topic = SourceArticleDescriptor(
            title="Bogus",
            content_locations=[uuid4(), uuid4()],
            tags=["noise"],
        )
        topic_list = TopicExtractionResponse(articles=[topic])
        llm_client = _mock_llm([topic_list.model_dump_json()])

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        topics = pipeline._extract_topics([source], llm_client, prompts)

        assert topics == []

    def test_failed_llm_call_skips_email(self):
        pipeline = self._make_pipeline()
        source = _make_source()
        llm_client = MagicMock()
        llm_client.complete.side_effect = RuntimeError("network error")

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        topics = pipeline._extract_topics([source], llm_client, prompts)

        assert topics == []


# ── _curate_articles ──────────────────────────────────────────────────────────


class TestCurateArticles:
    def _make_pipeline(self) -> EmailProcessingPipeline:
        with patch("polyglot_pigeon.scheduler.pipeline.get_config") as mock_cfg:
            mock_cfg.return_value = _mock_config()
            return EmailProcessingPipeline()

    def _make_topics(self, n: int = 3) -> list[SourceArticleDescriptor]:
        return [
            SourceArticleDescriptor(
                title=f"Article {i}",
                content_locations=[uuid4()],
                tags=["tag"],
            )
            for i in range(n)
        ]

    def test_returns_selected_ids_in_order(self):
        pipeline = self._make_pipeline()
        topics = self._make_topics(3)
        selected = [topics[1].article_id, topics[0].article_id]
        curation = CurationResponse(selected_ids=selected)
        llm_client = _mock_llm([curation.model_dump_json()])

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        result = pipeline._curate_articles(
            topics, max_articles=7, llm_client=llm_client, prompts=prompts,
        )

        assert result == selected

    def test_unknown_ids_dropped(self):
        pipeline = self._make_pipeline()
        topics = self._make_topics(2)
        curation = CurationResponse(selected_ids=[uuid4(), topics[0].article_id])
        llm_client = _mock_llm([curation.model_dump_json()])

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        result = pipeline._curate_articles(
            topics, max_articles=7, llm_client=llm_client, prompts=prompts,
        )

        assert result == [topics[0].article_id]

    def test_max_articles_cap_applied(self):
        pipeline = self._make_pipeline()
        topics = self._make_topics(5)
        curation = CurationResponse(selected_ids=[t.article_id for t in topics])
        llm_client = _mock_llm([curation.model_dump_json()])

        prompts = MagicMock()
        prompts.get.return_value = "prompt"

        result = pipeline._curate_articles(
            topics, max_articles=2, llm_client=llm_client, prompts=prompts,
        )

        assert len(result) == 2


# ── _reconstruct_content ──────────────────────────────────────────────────────


class TestReconstructContent:
    def _make_pipeline(self) -> EmailProcessingPipeline:
        with patch("polyglot_pigeon.scheduler.pipeline.get_config") as mock_cfg:
            mock_cfg.return_value = _mock_config()
            return EmailProcessingPipeline()

    def test_concatenates_chunks_in_order(self):
        pipeline = self._make_pipeline()

        chunk_id_1 = uuid4()
        chunk_id_2 = uuid4()
        source = ChunkedSourceEmail(
            email_id=uuid4(),
            sender="Test <test@example.com>",
            sender_name="Test",
            email_subject="Weekly",
            email_contents=[
                EmailChunk(chunk_id=chunk_id_1, text="First chunk."),
                EmailChunk(chunk_id=chunk_id_2, text="Second chunk."),
            ],
        )
        topic = SourceArticleDescriptor(
            title="My Article",
            content_locations=[chunk_id_1, chunk_id_2],
            tags=["news"],
        )
        topic.article_email = source.email_id

        articles = pipeline._reconstruct_content(
            selected_ids=[topic.article_id],
            topics=[topic],
            source_map={source.email_id: source},
        )

        assert len(articles) == 1
        assert "First chunk." in articles[0].content
        assert "Second chunk." in articles[0].content
        assert articles[0].title == "My Article"
        assert articles[0].sender_name == "Test"

    def test_missing_topic_skipped(self):
        pipeline = self._make_pipeline()
        unknown_id = uuid4()

        articles = pipeline._reconstruct_content(
            selected_ids=[unknown_id],
            topics=[],
            source_map={},
        )

        assert articles == []

    def test_missing_source_skipped(self):
        pipeline = self._make_pipeline()
        chunk_id = uuid4()
        topic = SourceArticleDescriptor(
            title="Orphan",
            content_locations=[chunk_id],
            tags=[],
        )
        # article_email points to a source that isn't in source_map
        topic.article_email = uuid4()

        articles = pipeline._reconstruct_content(
            selected_ids=[topic.article_id],
            topics=[topic],
            source_map={},
        )

        assert articles == []


# ── build_digest integration ──────────────────────────────────────────────────


class TestBuildDigestIntegration:
    """End-to-end build_digest with all LLM calls mocked via stage methods."""

    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_orchestrates_all_stages(self, mock_get_config):
        mock_get_config.return_value = _mock_config()
        pipeline = EmailProcessingPipeline()

        source = _make_source()
        article_id = uuid4()
        topic = MagicMock(spec=SourceArticleDescriptor)
        topic.article_id = article_id
        selected_article = MagicMock(spec=SelectedArticle)
        digest_content = _digest()

        pipeline._chunk_emails = MagicMock(return_value=[source])
        pipeline._extract_topics = MagicMock(return_value=[topic])
        pipeline._curate_articles = MagicMock(return_value=[article_id])
        pipeline._reconstruct_content = MagicMock(return_value=[selected_article])
        pipeline._transform_articles = MagicMock(return_value=digest_content)

        with patch("polyglot_pigeon.scheduler.pipeline.PromptManager"):
            with patch("polyglot_pigeon.scheduler.pipeline.create_llm_client"):
                result = pipeline.build_digest([MagicMock()])

        assert result.subject.startswith("Your German learning digest")
        pipeline._chunk_emails.assert_called_once()
        pipeline._extract_topics.assert_called_once()
        pipeline._curate_articles.assert_called_once()
        pipeline._reconstruct_content.assert_called_once()
        pipeline._transform_articles.assert_called_once()

    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_raises_if_no_chunks(self, mock_get_config):
        mock_get_config.return_value = _mock_config()
        pipeline = EmailProcessingPipeline()
        pipeline._chunk_emails = MagicMock(return_value=[])

        with patch("polyglot_pigeon.scheduler.pipeline.PromptManager"):
            with patch("polyglot_pigeon.scheduler.pipeline.create_llm_client"):
                with pytest.raises(ValueError, match="chunking"):
                    pipeline.build_digest([MagicMock()])

    @patch("polyglot_pigeon.scheduler.pipeline.get_config")
    def test_raises_if_no_topics(self, mock_get_config):
        mock_get_config.return_value = _mock_config()
        pipeline = EmailProcessingPipeline()
        pipeline._chunk_emails = MagicMock(return_value=[_make_source()])
        pipeline._extract_topics = MagicMock(return_value=[])

        with patch("polyglot_pigeon.scheduler.pipeline.PromptManager"):
            with patch("polyglot_pigeon.scheduler.pipeline.create_llm_client"):
                with pytest.raises(ValueError, match="topics"):
                    pipeline.build_digest([MagicMock()])
