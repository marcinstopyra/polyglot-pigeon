#!/usr/bin/env python3
"""
Test script to read emails from source email using EmailReader.

Usage:
    python utilities/read_emails.py -c config.yaml
    python utilities/read_emails.py -c config.yaml --fetch-days 7
    python utilities/read_emails.py -c config.yaml --fetch-days 3 --include-read
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polyglot_pigeon.config import ConfigLoader
from polyglot_pigeon.mail import EmailReader


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test script to read emails from source email"
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
        "--folder",
        default="INBOX",
        help="IMAP folder to read from (default: INBOX)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--max-body-length",
        type=int,
        default=500,
        help="Max characters to display for email body (default: 500)",
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

    # Override fetch_days if provided
    if args.fetch_days is not None:
        config.source_email.fetch_days = args.fetch_days

    print(f"Source email: {config.source_email.address}")
    print(f"IMAP server: {config.source_email.imap_server}:{config.source_email.imap_port}")
    print(f"Fetch days: {config.source_email.fetch_days}")
    print(f"Folder: {args.folder}")
    print(f"Unread only: {not args.include_read}")
    print("-" * 60)

    # Read emails
    reader = EmailReader(config.source_email)

    try:
        with reader:
            emails = reader.fetch_emails(
                folder=args.folder,
                unread_only=not args.include_read,
            )

            if not emails:
                print("\nNo emails found matching criteria.")
                return

            print(f"\nFound {len(emails)} email(s):\n")

            for i, email in enumerate(emails, 1):
                print(f"{'='*60}")
                print(f"Email {i}/{len(emails)}")
                print(f"{'='*60}")
                print(f"UID:     {email.uid}")
                print(f"From:    {email.sender}")
                print(f"Subject: {email.subject}")
                print(f"Date:    {email.date}")
                print(f"Has HTML: {email.body_html is not None and len(email.body_html) > 0}")
                print(f"\nBody (first {args.max_body_length} chars):")
                print("-" * 40)

                body = email.body_text or email.body_html or "(empty)"
                if len(body) > args.max_body_length:
                    body = body[:args.max_body_length] + "..."
                print(body)
                print()

    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
