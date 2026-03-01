#!/usr/bin/env python3
"""
Test script to run selected emails through the full processing pipeline.

Usage:
    python utilities/test_pipeline.py -c config.yaml --dry-run
    python utilities/test_pipeline.py -c config.yaml --dry-run --output-dir ./output
    python utilities/test_pipeline.py -c config.yaml --fetch-days 3 --max-emails 10
"""

import argparse
import logging
import sys
import uuid
from datetime import date
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polyglot_pigeon.config import ConfigLoader
from polyglot_pigeon.content import ContentCleaner
from polyglot_pigeon.llm import create_llm_client
from polyglot_pigeon.llm.models import LLMMessage, MessageRole
from polyglot_pigeon.mail import EmailReader, EmailSender
from polyglot_pigeon.prompts import PromptManager
from polyglot_pigeon.scheduler.pipeline import markdown_to_email_html


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def parse_selection(raw: str, count: int) -> list[int] | None:
    """Parse user input into 0-based indices. Returns None on invalid input.

    Accepts:
        'all'        → all indices
        '1,3,5'      → [0, 2, 4]
        '1 3 5'      → [0, 2, 4]
    """
    raw = raw.strip().lower()
    if raw == "all":
        return list(range(count))
    indices = []
    for part in raw.replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            return None
        if not (1 <= n <= count):
            return None
        indices.append(n - 1)
    return indices if indices else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run selected emails through the full processing pipeline"
    )
    parser.add_argument(
        "-c", "--config", required=True, help="Path to config.yaml file"
    )
    parser.add_argument(
        "--fetch-days",
        type=int,
        default=None,
        help="Number of days to fetch emails from (overrides config)",
    )
    parser.add_argument(
        "--include-read",
        action="store_true",
        help="Include already read emails (default: unread only)",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=10,
        help="Maximum number of emails to display (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Save digest as .md file instead of sending to target email",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save .md file when using --dry-run (default: current directory)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    loader = ConfigLoader()
    config = loader.load(config_path)

    if args.fetch_days is not None:
        config.source_email.fetch_days = args.fetch_days

    # Fetch emails
    print(f"Fetching emails from {config.source_email.address}...")
    reader = EmailReader(config.source_email)
    try:
        with reader:
            emails = reader.fetch_emails(unread_only=not args.include_read)
    except Exception as e:
        print(f"Error fetching emails: {e}")
        sys.exit(1)

    if not emails:
        print("No emails found.")
        return

    emails = emails[: args.max_emails]
    print(f"\nFound {len(emails)} email(s):\n")
    for i, email in enumerate(emails, 1):
        print(f"  [{i}] {email.subject}")
        print(f"      From: {email.sender}  |  Date: {email.date}")

    # Interactive batch selection
    print()
    while True:
        raw = input(
            f"Select emails for the batch (e.g. '1,3' or 'all'), or 'q' to quit: "
        ).strip()
        if raw.lower() == "q":
            print("Bye!")
            return

        indices = parse_selection(raw, len(emails))
        if indices is None:
            print(
                f"  Invalid selection. Enter numbers 1-{len(emails)},"
                " comma-separated, or 'all'."
            )
            continue

        selected = [emails[i] for i in indices]
        print(f"\nSelected {len(selected)} email(s):")
        for e in selected:
            print(f"  - {e.subject}")

        confirm = input("\nProceed? [y/n]: ").strip().lower()
        if confirm == "y":
            break
        print()

    # Step 1: Clean
    print("\nCleaning emails...")
    cleaned = ContentCleaner().clean(selected)
    if not cleaned:
        print("No content remained after cleaning. Exiting.")
        return
    print(f"  {len(cleaned)}/{len(selected)} email(s) had content after cleaning.")

    # Step 2: Format combined content for LLM
    content_parts = [
        f"Subject: {e.subject}\nFrom: {e.sender}\n\n{e.body}" for e in cleaned
    ]
    combined_content = "\n\n---\n\n".join(content_parts)

    # Step 3: Build prompts
    lang = config.language
    known_language = lang.known.name.title()
    target_language = lang.target.name.title()
    level = lang.level.name

    prompts = PromptManager()
    language_extra = prompts.get("language_extra")
    article_structure_extra = prompts.get("article_structure_extra")

    system_prompt = prompts.get(
        "system",
        known_language=known_language,
        target_language=target_language,
        level=level,
        language_extra=language_extra,
        article_structure_extra=article_structure_extra,
    )
    user_prompt = prompts.get("transform_user", content=combined_content)

    # Step 4: First LLM call — transform content to learning material
    print("\nTransforming content via LLM (call 1/2)...")
    llm_client = create_llm_client(config.llm)
    try:
        transform_response = llm_client.complete(
            [
                LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                LLMMessage(role=MessageRole.USER, content=user_prompt),
            ]
        )
    except Exception as e:
        print(f"LLM transform call failed: {e}")
        sys.exit(1)

    articles_text = transform_response.content

    # Step 5: Second LLM call — generate introduction
    print("Generating introduction via LLM (call 2/2)...")
    intro_system = prompts.get(
        "introduction_system",
        target_language=target_language,
        level=level,
        language_extra=language_extra,
    )
    intro_user = prompts.get("introduction_user", articles=articles_text)
    try:
        intro_response = llm_client.complete(
            [
                LLMMessage(role=MessageRole.SYSTEM, content=intro_system),
                LLMMessage(role=MessageRole.USER, content=intro_user),
            ]
        )
    except Exception as e:
        print(f"LLM introduction call failed: {e}")
        sys.exit(1)

    introduction = intro_response.content

    # Step 6: Compose final body
    body = f"{introduction}\n\n## Articles:\n\n{articles_text}"
    subject = f"Your {target_language} learning digest"

    # Step 6.5: Convert markdown to HTML
    body_html = markdown_to_email_html(body)

    # Step 7: Send or save
    if args.dry_run:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        short_id = uuid.uuid4().hex[:8]
        out_path = output_dir / f"pipeline_{today}_{short_id}.md"
        out_path.write_text(f"# {subject}\n\n{body}")
        print(f"\nDry run — digest saved to {out_path}")
    else:
        print(f"\nSending digest to {config.target_email.address}...")
        try:
            with EmailSender(config.target_email) as sender:
                sender.send(
                    to=config.target_email.address,
                    subject=subject,
                    body_text=body,
                    body_html=body_html,
                )
            print("Email sent successfully.")
        except Exception as e:
            print(f"Failed to send email: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
