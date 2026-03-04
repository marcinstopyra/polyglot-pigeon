import logging
import smtplib
import socket
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from polyglot_pigeon.models.configurations import TargetEmailConfig

log = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (socket.timeout, TimeoutError, OSError)


@dataclass
class InlineImage:
    """An inline image embedded in an HTML email via CID reference."""

    cid: str
    data: bytes
    mimetype: str = "image/png"


class EmailSender:
    """Sends emails via SMTP server."""

    def __init__(self, config: TargetEmailConfig):
        self.config = config
        self._connection: smtplib.SMTP | None = None

    def connect(self) -> None:
        """Establish connection to the SMTP server using STARTTLS."""
        log.info(f"Connecting to SMTP server: {self.config.smtp_server}")

        last_exception: Optional[Exception] = None
        for attempt in range(self.config.retry_count + 1):
            try:
                self._connection = smtplib.SMTP(
                    self.config.smtp_server, self.config.smtp_port
                )
                self._connection.starttls()
                self._connection.login(self.config.smtp_user, self.config.smtp_password)
                log.info("Successfully connected to SMTP server")
                return
            except RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                if attempt < self.config.retry_count:
                    log.warning(
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
                log.info("Disconnected from SMTP server")
            except smtplib.SMTPException as e:
                log.warning(f"Error during disconnect: {e}")
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
        inline_images: Optional[list[InlineImage]] = None,
    ) -> None:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body_text: Plain text body content
            body_html: Optional HTML body content
            inline_images: Optional list of images to embed via CID references
        """
        if not self._connection:
            raise RuntimeError("Not connected to SMTP server. Call connect() first.")

        if body_html and inline_images:
            msg = self._build_related_message(
                to, subject, body_text, body_html, inline_images
            )
        else:
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
                log.info(f"Email sent to {to}: {subject}")
                return
            except RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                if attempt < self.config.retry_count:
                    log.warning(
                        f"Send attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {self.config.retry_delay}s..."
                    )
                    time.sleep(self.config.retry_delay)

        raise last_exception  # type: ignore[misc]

    def _build_related_message(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: str,
        inline_images: list[InlineImage],
    ) -> MIMEMultipart:
        """Build a multipart/related message with inline image attachments."""
        related = MIMEMultipart("related")
        related["Subject"] = subject
        related["From"] = f"{self.config.sender_name} <{self.config.smtp_user}>"
        related["To"] = to

        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(body_text, "plain", "utf-8"))
        alternative.attach(MIMEText(body_html, "html", "utf-8"))
        related.attach(alternative)

        for img in inline_images:
            subtype = img.mimetype.split("/")[-1]
            mime_img = MIMEImage(img.data, subtype)
            mime_img.add_header("Content-ID", f"<{img.cid}>")
            mime_img.add_header(
                "Content-Disposition", "inline", filename=f"{img.cid}.{subtype}"
            )
            related.attach(mime_img)

        return related
