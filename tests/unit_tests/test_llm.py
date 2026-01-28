import sys
from unittest.mock import MagicMock, patch

import pytest

from polyglot_pigeon.llm import (
    ClaudeClient,
    LLMMessage,
    LLMResponse,
    MessageRole,
    OpenAIClient,
    PerplexityClient,
    create_llm_client,
)
from polyglot_pigeon.models.configurations import LLMConfig, LLMProvider


class TestLLMModels:
    """Test LLM Pydantic models."""

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
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )

        assert response.content == "Hello!"
        assert response.model == "gpt-4o"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.stop_reason == "end_turn"

    def test_llm_response_optional_fields(self):
        response = LLMResponse(content="Test", model="test-model")

        assert response.input_tokens is None
        assert response.output_tokens is None
        assert response.stop_reason is None


class TestLLMClientFactory:
    """Test LLM client factory function."""

    @pytest.fixture
    def claude_config(self):
        return LLMConfig(
            provider=LLMProvider.CLAUDE,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def openai_config(self):
        return LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def perplexity_config(self):
        return LLMConfig(
            provider=LLMProvider.PERPLEXITY,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    def test_create_claude_client(self, claude_config):
        client = create_llm_client(claude_config)

        assert isinstance(client, ClaudeClient)
        assert client.config == claude_config

    def test_create_openai_client(self, openai_config):
        client = create_llm_client(openai_config)

        assert isinstance(client, OpenAIClient)
        assert client.config == openai_config

    def test_create_perplexity_client(self, perplexity_config):
        client = create_llm_client(perplexity_config)

        assert isinstance(client, PerplexityClient)
        assert client.config == perplexity_config


class TestClaudeClient:
    """Test Claude client functionality."""

    @pytest.fixture
    def config(self):
        return LLMConfig(
            provider=LLMProvider.CLAUDE,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def client(self, config):
        return ClaudeClient(config)

    def test_default_model(self, client):
        assert client._default_model() == "claude-sonnet-4-20250514"

    def test_get_model_name_with_override(self, config):
        config.model = "claude-3-opus-20240229"
        client = ClaudeClient(config)

        assert client._get_model_name() == "claude-3-opus-20240229"

    def test_get_model_name_default(self, client):
        assert client._get_model_name() == "claude-sonnet-4-20250514"

    def test_complete_missing_package(self, client):
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError) as exc_info:
                client.complete([LLMMessage(role=MessageRole.USER, content="Hi")])

            assert "anthropic package is required" in str(exc_info.value)

    def test_complete_success(self, client):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello!")]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            messages = [
                LLMMessage(role=MessageRole.SYSTEM, content="Be helpful"),
                LLMMessage(role=MessageRole.USER, content="Hi"),
            ]
            response = client.complete(messages)

        assert response.content == "Hello!"
        assert response.model == "claude-sonnet-4-20250514"
        assert response.input_tokens == 10
        assert response.output_tokens == 5

        # Verify system message was separated
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "Be helpful"
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"


class TestOpenAIClient:
    """Test OpenAI client functionality."""

    @pytest.fixture
    def config(self):
        return LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def client(self, config):
        return OpenAIClient(config)

    def test_default_model(self, client):
        assert client._default_model() == "gpt-4o"

    def test_complete_missing_package(self, client):
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError) as exc_info:
                client.complete([LLMMessage(role=MessageRole.USER, content="Hi")])

            assert "openai package is required" in str(exc_info.value)

    def test_complete_success(self, client):
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(sys.modules, {"openai": mock_openai}):
            messages = [LLMMessage(role=MessageRole.USER, content="Hi")]
            response = client.complete(messages)

        assert response.content == "Hello!"
        assert response.model == "gpt-4o"
        assert response.input_tokens == 10
        assert response.output_tokens == 5


class TestPerplexityClient:
    """Test Perplexity client functionality."""

    @pytest.fixture
    def config(self):
        return LLMConfig(
            provider=LLMProvider.PERPLEXITY,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    @pytest.fixture
    def client(self, config):
        return PerplexityClient(config)

    def test_default_model(self, client):
        assert client._default_model() == "sonar-pro"

    def test_base_url(self, client):
        assert client.PERPLEXITY_BASE_URL == "https://api.perplexity.ai"

    def test_complete_uses_custom_base_url(self, client):
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "sonar-pro"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(sys.modules, {"openai": mock_openai}):
            messages = [LLMMessage(role=MessageRole.USER, content="Hi")]
            client.complete(messages)

        # Verify custom base URL was used
        mock_openai.OpenAI.assert_called_once_with(
            api_key="test-key", base_url="https://api.perplexity.ai"
        )


class TestLLMClientStreaming:
    """Test streaming functionality."""

    @pytest.fixture
    def config(self):
        return LLMConfig(
            provider=LLMProvider.CLAUDE,
            api_key="test-key",
            max_tokens=1024,
            temperature=0.7,
        )

    def test_stream_not_implemented(self, config):
        client = ClaudeClient(config)

        with pytest.raises(NotImplementedError) as exc_info:
            list(client.stream([LLMMessage(role=MessageRole.USER, content="Hi")]))

        assert "does not support streaming" in str(exc_info.value)

    def test_stream_async_not_implemented(self, config):
        import asyncio

        client = ClaudeClient(config)

        async def test_async():
            with pytest.raises(NotImplementedError) as exc_info:
                async for _ in client.stream_async(
                    [LLMMessage(role=MessageRole.USER, content="Hi")]
                ):
                    pass
            return exc_info

        exc_info = asyncio.run(test_async())
        assert "does not support async streaming" in str(exc_info.value)
