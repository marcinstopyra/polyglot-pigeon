"""Abstract LLM client and provider implementations."""

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator

from polyglot_pigeon.llm.models import LLMMessage, LLMResponse, MessageRole
from polyglot_pigeon.models.configurations import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base class for LLM API clients."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """Send a completion request to the LLM."""
        pass

    @abstractmethod
    async def complete_async(self, messages: list[LLMMessage]) -> LLMResponse:
        """Send an async completion request to the LLM."""
        pass

    def stream(self, messages: list[LLMMessage]) -> Iterator[str]:
        """Stream a completion response from the LLM."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support streaming"
        )

    async def stream_async(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        """Stream an async completion response from the LLM."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support async streaming"
        )
        yield  # Make this a generator


class ClaudeClient(LLMClient):
    """Client for Anthropic's Claude API (native SDK)."""

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package is required for Claude. "
                "Install with: pip install anthropic"
            ) from e

        client = anthropic.Anthropic(api_key=self.config.api_key)

        system_content = None
        conversation_messages = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_content = msg.content
            else:
                conversation_messages.append(
                    {"role": msg.role.name.lower(), "content": msg.content}
                )

        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": conversation_messages,
        }
        if system_content:
            kwargs["system"] = system_content
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature

        logger.debug(f"Sending request to Claude: {self.config.model}")
        response = client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )

    async def complete_async(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package is required for Claude. "
                "Install with: pip install anthropic"
            ) from e

        client = anthropic.AsyncAnthropic(api_key=self.config.api_key)

        system_content = None
        conversation_messages = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_content = msg.content
            else:
                conversation_messages.append(
                    {"role": msg.role.name.lower(), "content": msg.content}
                )

        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": conversation_messages,
        }
        if system_content:
            kwargs["system"] = system_content
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature

        logger.debug(f"Sending async request to Claude: {self.config.model}")
        response = await client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )


class OpenAICompatibleClient(LLMClient):
    """Client for any OpenAI-compatible API.

    Works with OpenAI, Perplexity, Ollama, or any endpoint that speaks
    the /v1/chat/completions protocol. Set config.url to override the
    default OpenAI base URL.
    """

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            ) from e

        kwargs = {"api_key": self.config.api_key}
        if self.config.url:
            kwargs["base_url"] = self.config.url

        client = openai.OpenAI(**kwargs)
        formatted_messages = [
            {"role": msg.role.name.lower(), "content": msg.content} for msg in messages
        ]

        logger.debug(
            f"Sending request to {self.config.url or 'OpenAI'}: {self.config.model}"
        )
        response = client.chat.completions.create(
            model=self.config.model,
            messages=formatted_messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            stop_reason=choice.finish_reason,
        )

    async def complete_async(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            ) from e

        kwargs = {"api_key": self.config.api_key}
        if self.config.url:
            kwargs["base_url"] = self.config.url

        client = openai.AsyncOpenAI(**kwargs)
        formatted_messages = [
            {"role": msg.role.name.lower(), "content": msg.content} for msg in messages
        ]

        logger.debug(
            f"Sending async request to {self.config.url or 'OpenAI'}: {self.config.model}"
        )
        response = await client.chat.completions.create(
            model=self.config.model,
            messages=formatted_messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage else None,
            output_tokens=response.usage.completion_tokens if response.usage else None,
            stop_reason=choice.finish_reason,
        )


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Create an LLM client from config.

    Routes to ClaudeClient when provider='claude', otherwise uses
    OpenAICompatibleClient (works with OpenAI, Perplexity, Ollama, etc.).
    """
    if config.provider and config.provider.lower() == "claude":
        logger.info(f"Creating Claude client: {config.model}")
        return ClaudeClient(config)

    logger.info(
        f"Creating OpenAI-compatible client: {config.model}"
        f" @ {config.url or 'OpenAI default'}"
    )
    return OpenAICompatibleClient(config)
