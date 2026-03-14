import sys
from unittest.mock import MagicMock, patch

import pytest

from polyglot_pigeon.llm import (
    ClaudeClient,
    LLMMessage,
    LLMResponse,
    MessageRole,
    OpenAICompatibleClient,
    create_llm_client,
)
from polyglot_pigeon.models.configurations import LLMConfig

# ── fixtures ──────────────────────────────────────────────────────────────────


def _config(**kwargs) -> LLMConfig:
    defaults = dict(api_key="test-key", model="claude-haiku-4-5-20251001")
    defaults.update(kwargs)
    return LLMConfig(**defaults)


# ── LLM models ────────────────────────────────────────────────────────────────


class TestLLMModels:
    def test_message_role_enum(self):
        assert MessageRole.SYSTEM.name == "SYSTEM"
        assert MessageRole.USER.name == "USER"
        assert MessageRole.ASSISTANT.name == "ASSISTANT"

    def test_llm_message_creation(self):
        msg = LLMMessage(role=MessageRole.USER, content="Hello, world!")

        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"

    def test_llm_message_case_insensitive_role(self):
        msg = LLMMessage(role="user", content="Test")

        assert msg.role == MessageRole.USER

    def test_llm_message_serialization(self):
        msg = LLMMessage(role=MessageRole.SYSTEM, content="Be helpful")
        data = msg.model_dump()

        assert data["role"] == "system"
        assert data["content"] == "Be helpful"

    def test_llm_response_creation(self):
        response = LLMResponse(
            content="Hello!",
            model="claude-haiku-4-5-20251001",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )

        assert response.content == "Hello!"
        assert response.model == "claude-haiku-4-5-20251001"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.stop_reason == "end_turn"

    def test_llm_response_optional_fields(self):
        response = LLMResponse(content="Test", model="test-model")

        assert response.input_tokens is None
        assert response.output_tokens is None
        assert response.stop_reason is None


# ── factory ───────────────────────────────────────────────────────────────────


class TestLLMClientFactory:
    def test_creates_claude_client_for_provider_claude(self):
        client = create_llm_client(_config(provider="claude"))

        assert isinstance(client, ClaudeClient)

    def test_creates_claude_client_case_insensitive(self):
        client = create_llm_client(_config(provider="CLAUDE"))

        assert isinstance(client, ClaudeClient)

    def test_creates_openai_compatible_client_by_default(self):
        client = create_llm_client(_config(model="gpt-4o"))

        assert isinstance(client, OpenAICompatibleClient)

    def test_creates_openai_compatible_client_with_url(self):
        client = create_llm_client(
            _config(model="sonar-pro", url="https://api.perplexity.ai")
        )

        assert isinstance(client, OpenAICompatibleClient)

    def test_creates_openai_compatible_client_for_ollama(self):
        client = create_llm_client(
            _config(model="llama3", url="http://localhost:11434/v1")
        )

        assert isinstance(client, OpenAICompatibleClient)


# ── ClaudeClient ──────────────────────────────────────────────────────────────


class TestClaudeClient:
    @pytest.fixture
    def client(self):
        return ClaudeClient(_config(provider="claude"))

    def test_complete_missing_package(self, client):
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError) as exc_info:
                client.complete([LLMMessage(role=MessageRole.USER, content="Hi")])

            assert "anthropic package is required" in str(exc_info.value)

    def test_complete_success(self, client):
        mock_anthropic = MagicMock()
        mock_api = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_api

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello!")]
        mock_response.model = "claude-haiku-4-5-20251001"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_api.messages.create.return_value = mock_response

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            response = client.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content="Be helpful"),
                    LLMMessage(role=MessageRole.USER, content="Hi"),
                ]
            )

        assert response.content == "Hello!"
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    def test_complete_separates_system_message(self, client):
        mock_anthropic = MagicMock()
        mock_api = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_api
        mock_api.messages.create.return_value = MagicMock(
            content=[MagicMock(text="ok")],
            model="m",
            usage=MagicMock(input_tokens=1, output_tokens=1),
            stop_reason="end_turn",
        )

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            client.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content="Be helpful"),
                    LLMMessage(role=MessageRole.USER, content="Hi"),
                ]
            )

        call_kwargs = mock_api.messages.create.call_args[1]
        assert call_kwargs["system"] == "Be helpful"
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"


# ── OpenAICompatibleClient ────────────────────────────────────────────────────


class TestOpenAICompatibleClient:
    @pytest.fixture
    def client(self):
        return OpenAICompatibleClient(_config(model="gpt-4o"))

    @pytest.fixture
    def perplexity_client(self):
        return OpenAICompatibleClient(
            _config(model="sonar-pro", url="https://api.perplexity.ai")
        )

    def test_complete_missing_package(self, client):
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError) as exc_info:
                client.complete([LLMMessage(role=MessageRole.USER, content="Hi")])

            assert "openai package is required" in str(exc_info.value)

    def test_complete_success(self, client):
        mock_openai = MagicMock()
        mock_api = MagicMock()
        mock_openai.OpenAI.return_value = mock_api

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_api.chat.completions.create.return_value = mock_response

        with patch.dict(sys.modules, {"openai": mock_openai}):
            response = client.complete(
                [LLMMessage(role=MessageRole.USER, content="Hi")]
            )

        assert response.content == "Hello!"
        assert response.model == "gpt-4o"
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    def test_complete_uses_no_base_url_by_default(self, client):
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = MagicMock(
            chat=MagicMock(
                completions=MagicMock(
                    create=MagicMock(
                        return_value=MagicMock(
                            choices=[
                                MagicMock(
                                    message=MagicMock(content="ok"),
                                    finish_reason="stop",
                                )
                            ],
                            model="gpt-4o",
                            usage=MagicMock(prompt_tokens=1, completion_tokens=1),
                        )
                    )
                )
            )
        )

        with patch.dict(sys.modules, {"openai": mock_openai}):
            client.complete([LLMMessage(role=MessageRole.USER, content="Hi")])

        call_kwargs = mock_openai.OpenAI.call_args[1]
        assert "base_url" not in call_kwargs

    def test_complete_uses_custom_base_url(self, perplexity_client):
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = MagicMock(
            chat=MagicMock(
                completions=MagicMock(
                    create=MagicMock(
                        return_value=MagicMock(
                            choices=[
                                MagicMock(
                                    message=MagicMock(content="ok"),
                                    finish_reason="stop",
                                )
                            ],
                            model="sonar-pro",
                            usage=MagicMock(prompt_tokens=1, completion_tokens=1),
                        )
                    )
                )
            )
        )

        with patch.dict(sys.modules, {"openai": mock_openai}):
            perplexity_client.complete(
                [LLMMessage(role=MessageRole.USER, content="Hi")]
            )

        call_kwargs = mock_openai.OpenAI.call_args[1]
        assert call_kwargs["base_url"] == "https://api.perplexity.ai"


# ── streaming ─────────────────────────────────────────────────────────────────


class TestLLMClientStreaming:
    def test_stream_not_implemented(self):
        client = ClaudeClient(_config(provider="claude"))

        with pytest.raises(NotImplementedError) as exc_info:
            list(client.stream([LLMMessage(role=MessageRole.USER, content="Hi")]))

        assert "does not support streaming" in str(exc_info.value)

    def test_stream_async_not_implemented(self):
        import asyncio

        client = ClaudeClient(_config(provider="claude"))

        async def test_async():
            with pytest.raises(NotImplementedError) as exc_info:
                async for _ in client.stream_async(
                    [LLMMessage(role=MessageRole.USER, content="Hi")]
                ):
                    pass
            return exc_info

        exc_info = asyncio.run(test_async())
        assert "does not support async streaming" in str(exc_info.value)
