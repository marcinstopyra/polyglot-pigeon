import socket
from unittest.mock import MagicMock, patch

import pytest

from polyglot_pigeon.mail import EmailSender
from polyglot_pigeon.models.configurations import TargetEmailConfig


@pytest.fixture
def target_config():
    return TargetEmailConfig(
        address="recipient@example.com",
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="test_password",
        sender_name="Polyglot Pigeon",
    )


@pytest.fixture
def mock_smtp():
    with patch("polyglot_pigeon.mail.sender.smtplib.SMTP") as mock:
        mock_connection = MagicMock()
        mock.return_value = mock_connection
        yield mock_connection


class TestEmailSender:
    """Test EmailSender connection management."""

    def test_init(self, target_config):
        sender = EmailSender(target_config)

        assert sender.config == target_config
        assert sender._connection is None

    def test_connect(self, target_config, mock_smtp):
        sender = EmailSender(target_config)

        sender.connect()

        assert sender._connection is mock_smtp
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("sender@example.com", "test_password")

    def test_disconnect(self, target_config, mock_smtp):
        sender = EmailSender(target_config)
        sender._connection = mock_smtp

        sender.disconnect()

        mock_smtp.quit.assert_called_once()
        assert sender._connection is None

    def test_disconnect_when_not_connected(self, target_config):
        sender = EmailSender(target_config)

        sender.disconnect()

        assert sender._connection is None

    def test_context_manager(self, target_config, mock_smtp):
        sender = EmailSender(target_config)

        with sender as s:
            assert s is sender
            assert s._connection is mock_smtp

        mock_smtp.quit.assert_called_once()


class TestSendEmail:
    """Test sending emails."""

    def test_send_not_connected_raises_error(self, target_config):
        sender = EmailSender(target_config)

        with pytest.raises(RuntimeError) as exc_info:
            sender.send(
                to="recipient@example.com",
                subject="Test",
                body_text="Hello",
            )

        assert "Not connected to SMTP server" in str(exc_info.value)

    def test_send_plain_text(self, target_config, mock_smtp):
        sender = EmailSender(target_config)
        sender._connection = mock_smtp

        sender.send(
            to="recipient@example.com",
            subject="Test Subject",
            body_text="Hello, this is a test.",
        )

        mock_smtp.send_message.assert_called_once()
        msg = mock_smtp.send_message.call_args[0][0]
        assert msg["Subject"] == "Test Subject"
        assert msg["To"] == "recipient@example.com"
        assert msg["From"] == "Polyglot Pigeon <sender@example.com>"
        assert "Hello, this is a test." in msg.get_content()

    def test_send_with_html(self, target_config, mock_smtp):
        sender = EmailSender(target_config)
        sender._connection = mock_smtp

        sender.send(
            to="recipient@example.com",
            subject="HTML Test",
            body_text="Plain text version",
            body_html="<html><body><p>HTML version</p></body></html>",
        )

        mock_smtp.send_message.assert_called_once()
        msg = mock_smtp.send_message.call_args[0][0]

        # Check that it's a multipart message
        assert msg.is_multipart()

        # Get the parts
        parts = list(msg.iter_parts())
        assert len(parts) == 2

        # First part should be plain text
        assert parts[0].get_content_type() == "text/plain"
        assert "Plain text version" in parts[0].get_content()

        # Second part should be HTML
        assert parts[1].get_content_type() == "text/html"
        assert "HTML version" in parts[1].get_content()

    def test_send_via_context_manager(self, target_config, mock_smtp):
        sender = EmailSender(target_config)

        with sender:
            sender.send(
                to="test@example.com",
                subject="Context Manager Test",
                body_text="Sent via context manager",
            )

        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()


class TestRetryMechanism:
    """Test retry behavior on network timeouts."""

    @pytest.fixture
    def retry_config(self):
        return TargetEmailConfig(
            address="recipient@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_user="sender@example.com",
            smtp_password="test_password",
            retry_count=2,
            retry_delay=0.01,  # Fast retries for tests
        )

    @patch("polyglot_pigeon.mail.sender.time.sleep")
    @patch("polyglot_pigeon.mail.sender.smtplib.SMTP")
    def test_connect_retries_on_timeout(
        self, mock_smtp_class, mock_sleep, retry_config
    ):
        mock_connection = MagicMock()
        mock_smtp_class.side_effect = [
            socket.timeout("Connection timed out"),
            socket.timeout("Connection timed out"),
            mock_connection,
        ]

        sender = EmailSender(retry_config)
        sender.connect()

        assert mock_smtp_class.call_count == 3
        assert mock_sleep.call_count == 2
        assert sender._connection is mock_connection

    @patch("polyglot_pigeon.mail.sender.time.sleep")
    @patch("polyglot_pigeon.mail.sender.smtplib.SMTP")
    def test_connect_raises_after_all_retries_exhausted(
        self, mock_smtp_class, mock_sleep, retry_config
    ):
        mock_smtp_class.side_effect = socket.timeout("Connection timed out")

        sender = EmailSender(retry_config)

        with pytest.raises(socket.timeout):
            sender.connect()

        assert mock_smtp_class.call_count == 3  # 1 initial + 2 retries
        assert mock_sleep.call_count == 2

    @patch("polyglot_pigeon.mail.sender.time.sleep")
    def test_send_retries_on_timeout(self, mock_sleep, retry_config):
        with patch("polyglot_pigeon.mail.sender.smtplib.SMTP") as mock_smtp_class:
            mock_connection = MagicMock()
            mock_smtp_class.return_value = mock_connection
            mock_connection.send_message.side_effect = [
                socket.timeout("Send timed out"),
                socket.timeout("Send timed out"),
                None,  # Success on third attempt
            ]

            sender = EmailSender(retry_config)
            sender.connect()
            sender.send(to="test@example.com", subject="Test", body_text="Hello")

            assert mock_connection.send_message.call_count == 3
            assert mock_sleep.call_count == 2

    @patch("polyglot_pigeon.mail.sender.time.sleep")
    def test_send_raises_after_all_retries_exhausted(self, mock_sleep, retry_config):
        with patch("polyglot_pigeon.mail.sender.smtplib.SMTP") as mock_smtp_class:
            mock_connection = MagicMock()
            mock_smtp_class.return_value = mock_connection
            mock_connection.send_message.side_effect = socket.timeout("Send timed out")

            sender = EmailSender(retry_config)
            sender.connect()

            with pytest.raises(socket.timeout):
                sender.send(to="test@example.com", subject="Test", body_text="Hello")

            assert mock_connection.send_message.call_count == 3

    @patch("polyglot_pigeon.mail.sender.time.sleep")
    @patch("polyglot_pigeon.mail.sender.smtplib.SMTP")
    def test_connect_retries_on_os_error(
        self, mock_smtp_class, mock_sleep, retry_config
    ):
        mock_connection = MagicMock()
        mock_smtp_class.side_effect = [
            OSError("Network unreachable"),
            mock_connection,
        ]

        sender = EmailSender(retry_config)
        sender.connect()

        assert mock_smtp_class.call_count == 2
        assert sender._connection is mock_connection
