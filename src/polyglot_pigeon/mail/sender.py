import logging
import smtplib
import socket
import time
from email.message import EmailMessage
from typing import Optional

from polyglot_pigeon.models.configurations import TargetEmailConfig

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (socket.timeout, TimeoutError, OSError)


class EmailSender:
    """Sends emails via SMTP server."""

    def __init__(self, config: TargetEmailConfig):
        self.config = config
        self._connection: smtplib.SMTP | None = None

    def connect(self) -> None:
        """Establish connection to the SMTP server using STARTTLS."""
        logger.info(f"Connecting to SMTP server: {self.config.smtp_server}")

        last_exception: Optional[Exception] = None
        for attempt in range(self.config.retry_count + 1):
            try:
                self._connection = smtplib.SMTP(
                    self.config.smtp_server, self.config.smtp_port
                )
                self._connection.starttls()
                self._connection.login(self.config.smtp_user, self.config.smtp_password)
                logger.info("Successfully connected to SMTP server")
                return
            except RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                if attempt < self.config.retry_count:
                    logger.warning(
                        f"Connection attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {self.config.retry_delay}s..."
                    )
                    time.sleep(self.config.retry_delay)

        raise last_exception  # type: ignore[misc]

    def disconnect(self) -> None:
        """Close the SMTP connection."""
        if self._connection:
            try:
                self._connection.quit()
                logger.info("Disconnected from SMTP server")
            except smtplib.SMTPException as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._connection = None

    def __enter__(self) -> "EmailSender":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body_text: Plain text body content
            body_html: Optional HTML body content (creates multipart/alternative)
        """
        if not self._connection:
            raise RuntimeError("Not connected to SMTP server. Call connect() first.")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{self.config.sender_name} <{self.config.smtp_user}>"
        msg["To"] = to

        msg.set_content(body_text)

        if body_html:
            msg.add_alternative(body_html, subtype="html")

        last_exception: Optional[Exception] = None
        for attempt in range(self.config.retry_count + 1):
            try:
                self._connection.send_message(msg)
                logger.info(f"Email sent to {to}: {subject}")
                return
            except RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                if attempt < self.config.retry_count:
                    logger.warning(
                        f"Send attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {self.config.retry_delay}s..."
                    )
                    time.sleep(self.config.retry_delay)

        raise last_exception  # type: ignore[misc]
