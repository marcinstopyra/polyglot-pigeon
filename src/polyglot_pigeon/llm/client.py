"""Abstract LLM client and provider implementations."""

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator

from polyglot_pigeon.llm.models import LLMMessage, LLMResponse, MessageRole
from polyglot_pigeon.models.configurations import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base class for LLM API clients."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """
        Send a completion request to the LLM.

        Args:
            messages: List of messages forming the conversation.

        Returns:
            LLMResponse with the model's response.
        """
        pass

    @abstractmethod
    async def complete_async(self, messages: list[LLMMessage]) -> LLMResponse:
        """
        Send an async completion request to the LLM.

        Args:
            messages: List of messages forming the conversation.

        Returns:
            LLMResponse with the model's response.
        """
        pass

    def stream(self, messages: list[LLMMessage]) -> Iterator[str]:
        """
        Stream a completion response from the LLM.

        Args:
            messages: List of messages forming the conversation.

        Yields:
            String chunks of the response as they arrive.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support streaming"
        )

    async def stream_async(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        """
        Stream an async completion response from the LLM.

        Args:
            messages: List of messages forming the conversation.

        Yields:
            String chunks of the response as they arrive.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support async streaming"
        )
        yield  # Make this a generator

    def _get_model_name(self) -> str:
        """Get the model name to use, falling back to provider default."""
        if self.config.model:
            return self.config.model
        return self._default_model()

    @abstractmethod
    def _default_model(self) -> str:
        """Return the default model for this provider."""
        pass


class ClaudeClient(LLMClient):
    """Client for Anthropic's Claude API."""

    def _default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package is required for Claude. "
                "Install with: pip install anthropic"
            ) from e

        client = anthropic.Anthropic(api_key=self.config.api_key)

        # Separate system message from conversation
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
            "model": self._get_model_name(),
            "max_tokens": self.config.max_tokens,
            "messages": conversation_messages,
        }
        if system_content:
            kwargs["system"] = system_content
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature

        logger.debug(f"Sending request to Claude: {self._get_model_name()}")
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
            "model": self._get_model_name(),
            "max_tokens": self.config.max_tokens,
            "messages": conversation_messages,
        }
        if system_content:
            kwargs["system"] = system_content
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature

        logger.debug(f"Sending async request to Claude: {self._get_model_name()}")
        response = await client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )


class OpenAIClient(LLMClient):
    """Client for OpenAI's API."""

    def _default_model(self) -> str:
        return "gpt-4o"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai package is required for OpenAI. "
                "Install with: pip install openai"
            ) from e

        client = openai.OpenAI(api_key=self.config.api_key)

        formatted_messages = [
            {"role": msg.role.name.lower(), "content": msg.content} for msg in messages
        ]

        logger.debug(f"Sending request to OpenAI: {self._get_model_name()}")
        response = client.chat.completions.create(
            model=self._get_model_name(),
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
                "openai package is required for OpenAI. "
                "Install with: pip install openai"
            ) from e

        client = openai.AsyncOpenAI(api_key=self.config.api_key)

        formatted_messages = [
            {"role": msg.role.name.lower(), "content": msg.content} for msg in messages
        ]

        logger.debug(f"Sending async request to OpenAI: {self._get_model_name()}")
        response = await client.chat.completions.create(
            model=self._get_model_name(),
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


class PerplexityClient(LLMClient):
    """Client for Perplexity's API (OpenAI-compatible)."""

    PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

    def _default_model(self) -> str:
        return "sonar-pro"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai package is required for Perplexity. "
                "Install with: pip install openai"
            ) from e

        client = openai.OpenAI(
            api_key=self.config.api_key, base_url=self.PERPLEXITY_BASE_URL
        )

        formatted_messages = [
            {"role": msg.role.name.lower(), "content": msg.content} for msg in messages
        ]

        logger.debug(f"Sending request to Perplexity: {self._get_model_name()}")
        response = client.chat.completions.create(
            model=self._get_model_name(),
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
                "openai package is required for Perplexity. "
                "Install with: pip install openai"
            ) from e

        client = openai.AsyncOpenAI(
            api_key=self.config.api_key, base_url=self.PERPLEXITY_BASE_URL
        )

        formatted_messages = [
            {"role": msg.role.name.lower(), "content": msg.content} for msg in messages
        ]

        logger.debug(f"Sending async request to Perplexity: {self._get_model_name()}")
        response = await client.chat.completions.create(
            model=self._get_model_name(),
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
    """
    Factory function to create an LLM client based on the provider.

    Args:
        config: LLM configuration containing provider and credentials.

    Returns:
        An LLMClient instance for the specified provider.

    Raises:
        ValueError: If the provider is not supported.
    """
    provider_map: dict[LLMProvider, type[LLMClient]] = {
        LLMProvider.CLAUDE: ClaudeClient,
        LLMProvider.OPENAI: OpenAIClient,
        LLMProvider.PERPLEXITY: PerplexityClient,
    }

    client_class = provider_map.get(config.provider)
    if client_class is None:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")

    logger.info(f"Creating LLM client for provider: {config.provider.name}")
    return client_class(config)
