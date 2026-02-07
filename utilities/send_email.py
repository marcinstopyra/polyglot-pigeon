#!/usr/bin/env python3
"""
Test script to send emails using EmailSender.

Usage:
    python utilities/send_email.py -c config.yaml email.json
    python utilities/send_email.py -c config.yaml email.json --dry-run
    python utilities/send_email.py -c config.yaml email.json -v

Example email.json:
{
    "recipient": "user@example.com",
    "subject": "Test Email",
    "body_text": "Hello, this is a test email.",
    "body_html": "<h1>Hello</h1><p>This is a test email.</p>"
}
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from polyglot_pigeon.config import ConfigLoader
from polyglot_pigeon.mail import EmailSender


class EmailInput(BaseModel):
    """Input model for email content.

    Attributes:
        recipient: Email address to send to
        subject: Email subject line
        body_text: Plain text email body
        body_html: Optional HTML email body (creates multipart/alternative)
    """

    recipient: str
    subject: str
    body_text: str
    body_html: Optional[str] = None


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test script to send emails using EmailSender"
    )
    parser.add_argument(
        "-c", "--config", required=True, help="Path to config.yaml file"
    )
    parser.add_argument(
        "email_json",
        help="Path to JSON file with email content (recipient, subject, body_text, body_html)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without actually sending",
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

    # Load email input
    email_json_path = Path(args.email_json)
    if not email_json_path.exists():
        print(f"Error: Email JSON file not found: {email_json_path}")
        sys.exit(1)

    try:
        with open(email_json_path) as f:
            email_data = json.load(f)
        email_input = EmailInput(**email_data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {email_json_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Invalid email input: {e}")
        sys.exit(1)

    # Display info
    print(f"SMTP server: {config.target_email.smtp_server}:{config.target_email.smtp_port}")
    print(f"From: {config.target_email.sender_name} <{config.target_email.smtp_user}>")
    print(f"To: {email_input.recipient}")
    print(f"Subject: {email_input.subject}")
    print(f"Retry: {config.target_email.retry_count} attempts, {config.target_email.retry_delay}s delay")
    print(f"Has HTML: {email_input.body_html is not None}")
    print("-" * 60)
    print("Body preview (first 200 chars):")
    body_preview = email_input.body_text[:200]
    print(body_preview + "..." if len(email_input.body_text) > 200 else body_preview)
    print("-" * 60)

    if args.dry_run:
        print("\n[DRY RUN] Email not sent.")
        return

    # Confirm before sending
    try:
        confirm = input("\nSend this email? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)

    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    # Send email
    sender = EmailSender(config.target_email)

    try:
        with sender:
            sender.send(
                to=email_input.recipient,
                subject=email_input.subject,
                body_text=email_input.body_text,
                body_html=email_input.body_html,
            )
        print("\nEmail sent successfully!")

    except Exception as e:
        print(f"\nError sending email: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
