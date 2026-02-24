#!/usr/bin/env python3
"""
Test script to fetch emails, clean them with ContentCleaner, and save to .md file.

Usage:
    python utilities/test_cleaner.py -c config.yaml
    python utilities/test_cleaner.py -c config.yaml --fetch-days 3 --max-emails 10
    python utilities/test_cleaner.py -c config.yaml --output-dir ./output
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
from polyglot_pigeon.mail import EmailReader


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch emails, clean with ContentCleaner, save to .md file"
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
        default=5,
        help="Maximum number of emails to display (default: 5)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save cleaned .md file (default: current directory)",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Also save the original email body alongside the cleaned output",
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

    # Limit and display
    emails = emails[: args.max_emails]
    print(f"\nFound {len(emails)} email(s):\n")

    for i, email in enumerate(emails, 1):
        print(f"  [{i}] {email.subject}")
        print(f"      From: {email.sender}  |  Date: {email.date}")

    # Interactive selection loop
    cleaner = ContentCleaner()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    while True:
        choice = input(
            f"Pick an email to clean (1-{len(emails)}), or 'q' to quit: "
        ).strip()
        if choice.lower() == "q":
            print("Bye!")
            return
        try:
            idx = int(choice)
            if not (1 <= idx <= len(emails)):
                print(f"  Please enter a number between 1 and {len(emails)}")
                continue
        except ValueError:
            print("  Invalid input. Enter a number or 'q'.")
            continue

        selected = emails[idx - 1]
        print(f"\nCleaning: {selected.subject}")

        cleaned = cleaner.clean([selected])

        if not cleaned:
            print("  Email had no content after cleaning.\n")
            continue

        result = cleaned[0]

        output = f"# {result.subject}\n\n"
        output += f"**From:** {result.sender}\n\n"
        output += "---\n\n"
        output += result.body

        today = date.today().isoformat()
        short_id = uuid.uuid4().hex[:8]
        base = f"email_{today}_{short_id}"

        cleaned_path = output_dir / f"{base}_cleaned.md"
        cleaned_path.write_text(output)
        print(f"  Cleaned → {cleaned_path}")

        if args.save_raw:
            if selected.body_html:
                raw_path = output_dir / f"{base}_original.html"
                raw_path.write_text(selected.body_html)
            else:
                raw_path = output_dir / f"{base}_original.txt"
                raw_path.write_text(selected.body_text or "")
            print(f"  Original → {raw_path}")

        print()


if __name__ == "__main__":
    main()
