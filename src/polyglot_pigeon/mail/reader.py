import email
import imaplib
import logging
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.message import Message

from polyglot_pigeon.models.configurations import SourceEmailConfig
from polyglot_pigeon.models.models import Email

logger = logging.getLogger(__name__)


class EmailReader:
    """Reads emails from an IMAP server."""

    def __init__(self, config: SourceEmailConfig):
        self.config = config
        self._connection: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        """Establish connection to the IMAP server."""
        logger.info(f"Connecting to IMAP server: {self.config.imap_server}")
        self._connection = imaplib.IMAP4_SSL(
            self.config.imap_server, self.config.imap_port
        )
        self._connection.login(self.config.address, self.config.app_password)
        logger.info("Successfully connected to IMAP server")

    def disconnect(self) -> None:
        """Close the IMAP connection."""
        if self._connection:
            try:
                self._connection.logout()
                logger.info("Disconnected from IMAP server")
            except imaplib.IMAP4.error as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._connection = None

    def __enter__(self) -> "EmailReader":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def fetch_emails(
        self, folder: str = "INBOX", unread_only: bool = True
    ) -> list[Email]:
        """
        Fetch emails from the specified folder.

        Args:
            folder: IMAP folder to read from (default: INBOX)
            unread_only: If True, only fetch unread emails

        Returns:
            List of Email objects
        """
        if not self._connection:
            raise RuntimeError("Not connected to IMAP server. Call connect() first.")

        self._connection.select(folder)

        # Build search criteria
        search_criteria = self._build_search_criteria(unread_only)
        logger.debug(f"Searching with criteria: {search_criteria}")

        status, message_ids = self._connection.search(None, search_criteria)
        if status != "OK":
            logger.error(f"Failed to search emails: {status}")
            return []

        email_uids = message_ids[0].split()
        logger.info(f"Found {len(email_uids)} emails matching criteria")

        emails = []
        for uid in email_uids:
            email_obj = self._fetch_single_email(uid)
            if email_obj:
                emails.append(email_obj)

        return emails

    def _build_search_criteria(self, unread_only: bool) -> str:
        """Build IMAP search criteria string."""
        criteria_parts = []

        if unread_only:
            criteria_parts.append("UNSEEN")

        # Filter by date based on fetch_days config
        if self.config.fetch_days > 0:
            since_date = datetime.now(timezone.utc) - timedelta(
                days=self.config.fetch_days
            )
            date_str = since_date.strftime("%d-%b-%Y")
            criteria_parts.append(f'SINCE "{date_str}"')

        if not criteria_parts:
            return "ALL"

        return "(" + " ".join(criteria_parts) + ")"

    def _fetch_single_email(self, uid: bytes) -> Email | None:
        """Fetch and parse a single email by UID."""
        try:
            status, msg_data = self._connection.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                return None

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            return Email(
                uid=uid.decode(),
                subject=self._decode_header(msg["Subject"]),
                sender=self._decode_header(msg["From"]),
                date=self._parse_date(msg["Date"]),
                body_text=self._get_body(msg, "text/plain"),
                body_html=self._get_body(msg, "text/html"),
            )
        except Exception as e:
            logger.error(f"Error fetching email {uid}: {e}")
            return None

    def _decode_header(self, header_value: str | None) -> str:
        """Decode an email header value."""
        if not header_value:
            return ""

        decoded_parts = decode_header(header_value)
        result = []
        for content, charset in decoded_parts:
            if isinstance(content, bytes):
                result.append(content.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(content)
        return "".join(result)

    def _parse_date(self, date_str: str | None) -> datetime:
        """Parse email date string to datetime."""
        if not date_str:
            return datetime.now(timezone.utc)

        try:
            parsed = email.utils.parsedate_to_datetime(date_str)
            return parsed
        except (ValueError, TypeError):
            logger.warning(f"Could not parse date: {date_str}")
            return datetime.now(timezone.utc)

    def _get_body(self, msg: Message, content_type: str) -> str:
        """Extract body content of specified type from email."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == content_type:
                    return self._decode_payload(part)
        elif msg.get_content_type() == content_type:
            return self._decode_payload(msg)

        return ""

    def _decode_payload(self, part: Message) -> str:
        """Decode email part payload to string."""
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""

        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            return payload.decode("utf-8", errors="replace")

    def mark_as_read(self, uids: list[str], folder: str = "INBOX") -> None:
        """Mark emails as read (add SEEN flag)."""
        if not self._connection:
            raise RuntimeError("Not connected to IMAP server.")

        self._connection.select(folder)
        for uid in uids:
            self._connection.store(uid.encode(), "+FLAGS", "\\Seen")
            logger.debug(f"Marked email {uid} as read")

    def add_label(self, uids: list[str], label: str, folder: str = "INBOX") -> None:
        """
        Add a label/tag to emails (Gmail-specific).

        Args:
            uids: List of email UIDs
            label: Label name to add (e.g., "Processed")
            folder: IMAP folder to select (default: INBOX)
        """
        if not self._connection:
            raise RuntimeError("Not connected to IMAP server.")

        self._connection.select(folder)
        for uid in uids:
            try:
                self._connection.store(uid.encode(), "+X-GM-LABELS", f'"{label}"')
                logger.debug(f"Added label '{label}' to email {uid}")
            except imaplib.IMAP4.error as e:
                logger.warning(f"Could not add label to {uid}: {e}")
