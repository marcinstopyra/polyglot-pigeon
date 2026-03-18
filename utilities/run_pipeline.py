#!/usr/bin/env python3
"""
Interactive script to run selected emails through the full processing pipeline.

Usage:
    python utilities/run_pipeline.py -c config.yaml --dry-run
    python utilities/run_pipeline.py -c config.yaml --dry-run --output-dir ./output
    python utilities/run_pipeline.py -c config.yaml --fetch-days 3 --max-emails 10

Prompt overrides are configured via `pipeline.prompts_path` in config.yaml.
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
from polyglot_pigeon.mail import EmailReader
from polyglot_pigeon.scheduler.pipeline import EmailProcessingPipeline


def setup_logging(level: int = logging.INFO) -> None:
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
        help="Save digest as .html/.txt files instead of sending to target email",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save output files when using --dry-run (default: current directory)",
    )
    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    loader = ConfigLoader()
    config = loader.load(config_path)

    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    setup_logging(log_level)

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

    # Build digest
    print("\nBuilding digest...")
    pipeline = EmailProcessingPipeline()
    try:
        digest = pipeline.build_digest(selected)
    except Exception as e:
        print(f"Failed to build digest: {e}")
        sys.exit(1)

    # Send or save
    if args.dry_run:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        short_id = uuid.uuid4().hex[:8]
        stem = f"pipeline_{today}_{short_id}"
        txt_path = output_dir / f"{stem}.txt"
        html_path = output_dir / f"{stem}.html"
        txt_path.write_text(f"{digest.subject}\n\n{digest.body_text}")
        html_path.write_text(digest.body_html)
        print(f"\nDry run — digest saved to:")
        print(f"  {txt_path}")
        print(f"  {html_path}")
    else:
        print(f"\nSending digest to {config.target_email.address}...")
        result = pipeline.send_target_email(digest)
        if result.errors:
            print(f"Failed to send email: {result.errors[0]}")
            sys.exit(1)
        print("Email sent successfully.")


if __name__ == "__main__":
    main()
