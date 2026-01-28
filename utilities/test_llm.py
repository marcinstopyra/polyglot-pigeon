#!/usr/bin/env python3
"""
Test script to interact with LLM providers.

Usage:
    python utilities/test_llm.py -c config.yaml
    python utilities/test_llm.py -c config.yaml --provider claude --model claude-3-haiku-20240307
    python utilities/test_llm.py -c config.yaml --prompt "Translate 'hello' to German"
    python utilities/test_llm.py --provider openai --api-key $OPENAI_API_KEY --prompt "Say hi"
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polyglot_pigeon.llm import LLMMessage, MessageRole, create_llm_client
from polyglot_pigeon.models.configurations import LLMConfig, LLMProvider


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def get_config_from_args(args) -> LLMConfig:
    """Build LLMConfig from command line args or config file."""
    if args.config:
        from polyglot_pigeon.config import ConfigLoader

        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}")
            sys.exit(1)

        loader = ConfigLoader()
        full_config = loader.load(config_path)
        llm_config = full_config.llm

        # Override with CLI args if provided
        if args.provider:
            llm_config.provider = LLMProvider[args.provider.upper()]
        if args.api_key:
            llm_config.api_key = args.api_key
        if args.model:
            llm_config.model = args.model
        if args.max_tokens:
            llm_config.max_tokens = args.max_tokens
        if args.temperature is not None:
            llm_config.temperature = args.temperature

        return llm_config

    # Build config from CLI args only
    if not args.provider:
        print("Error: --provider is required when not using a config file")
        sys.exit(1)
    if not args.api_key:
        print("Error: --api-key is required when not using a config file")
        sys.exit(1)

    return LLMConfig(
        provider=LLMProvider[args.provider.upper()],
        api_key=args.api_key,
        model=args.model,
        max_tokens=args.max_tokens or 1024,
        temperature=args.temperature if args.temperature is not None else 0.7,
    )


def interactive_mode(client, system_prompt: str | None = None) -> None:
    """Run interactive chat session."""
    print("\nInteractive mode. Type 'quit' or 'exit' to end.")
    print("Type 'clear' to reset conversation.")
    print("-" * 60)

    messages = []
    if system_prompt:
        messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system_prompt))
        print(f"System prompt: {system_prompt}\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "clear":
            messages = []
            if system_prompt:
                messages.append(
                    LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)
                )
            print("Conversation cleared.")
            continue

        messages.append(LLMMessage(role=MessageRole.USER, content=user_input))

        try:
            response = client.complete(messages)
            print(f"\nAssistant: {response.content}")

            if response.input_tokens or response.output_tokens:
                print(
                    f"\n[tokens: {response.input_tokens} in / {response.output_tokens} out]"
                )

            messages.append(
                LLMMessage(role=MessageRole.ASSISTANT, content=response.content)
            )

        except Exception as e:
            print(f"\nError: {e}")
            # Remove the failed user message
            messages.pop()


def single_prompt_mode(
    client, prompt: str, system_prompt: str | None = None
) -> None:
    """Run single prompt and exit."""
    messages = []
    if system_prompt:
        messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system_prompt))

    messages.append(LLMMessage(role=MessageRole.USER, content=prompt))

    print(f"Prompt: {prompt}")
    if system_prompt:
        print(f"System: {system_prompt}")
    print("-" * 60)

    try:
        response = client.complete(messages)
        print(f"\nResponse:\n{response.content}")
        print("-" * 60)
        print(f"Model: {response.model}")
        if response.input_tokens or response.output_tokens:
            print(f"Tokens: {response.input_tokens} in / {response.output_tokens} out")
        if response.stop_reason:
            print(f"Stop reason: {response.stop_reason}")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test script to interact with LLM providers"
    )
    parser.add_argument(
        "-c", "--config", help="Path to config.yaml file (optional)"
    )
    parser.add_argument(
        "--provider",
        choices=["claude", "openai", "perplexity"],
        help="LLM provider (required if no config file)",
    )
    parser.add_argument(
        "--api-key",
        help="API key (required if no config file)",
    )
    parser.add_argument(
        "--model",
        help="Model name (optional, uses provider default)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="Max tokens for response (default: 1024)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Temperature for sampling (default: 0.7)",
    )
    parser.add_argument(
        "--prompt",
        help="Single prompt to send (if not provided, enters interactive mode)",
    )
    parser.add_argument(
        "--system",
        help="System prompt to use",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Build config
    llm_config = get_config_from_args(args)

    print(f"Provider: {llm_config.provider.name}")
    print(f"Model: {llm_config.model or '(default)'}")
    print(f"Max tokens: {llm_config.max_tokens}")
    print(f"Temperature: {llm_config.temperature}")
    print("-" * 60)

    # Create client
    try:
        client = create_llm_client(llm_config)
    except Exception as e:
        print(f"Error creating client: {e}")
        sys.exit(1)

    # Run in appropriate mode
    if args.prompt:
        single_prompt_mode(client, args.prompt, args.system)
    else:
        interactive_mode(client, args.system)


if __name__ == "__main__":
    main()
