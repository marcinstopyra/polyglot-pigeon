from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from polyglot_pigeon.email import EmailReader
from polyglot_pigeon.models.configurations import SourceEmailConfig
from polyglot_pigeon.models.models import Email


class TestEmailReader:
    """Test EmailReader functionality."""

    @pytest.fixture
    def source_config(self):
        return SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
            imap_server="imap.example.com",
            imap_port=993,
            fetch_days=7,
            mark_as_read=True,
        )

    @pytest.fixture
    def email_reader(self, source_config):
        return EmailReader(source_config)

    @pytest.fixture
    def mock_imap(self):
        with patch("polyglot_pigeon.email.reader.imaplib.IMAP4_SSL") as mock:
            mock_connection = MagicMock()
            mock.return_value = mock_connection
            yield mock_connection

    def test_init(self, email_reader, source_config):
        assert email_reader.config == source_config
        assert email_reader._connection is None

    def test_connect(self, email_reader, mock_imap):
        email_reader.connect()

        assert email_reader._connection is mock_imap
        mock_imap.login.assert_called_once_with("test@example.com", "test_password")

    def test_disconnect(self, email_reader, mock_imap):
        email_reader._connection = mock_imap

        email_reader.disconnect()

        mock_imap.logout.assert_called_once()
        assert email_reader._connection is None

    def test_disconnect_when_not_connected(self, email_reader):
        email_reader.disconnect()
        assert email_reader._connection is None

    def test_context_manager(self, email_reader, mock_imap):
        with email_reader as reader:
            assert reader is email_reader
            assert reader._connection is mock_imap

        mock_imap.logout.assert_called_once()

    def test_fetch_emails_not_connected_raises_error(self, email_reader):
        with pytest.raises(RuntimeError) as exc_info:
            email_reader.fetch_emails()

        assert "Not connected to IMAP server" in str(exc_info.value)

    def test_mark_as_read_not_connected_raises_error(self, email_reader):
        with pytest.raises(RuntimeError) as exc_info:
            email_reader.mark_as_read(["1", "2"])

        assert "Not connected to IMAP server" in str(exc_info.value)

    def test_add_label_not_connected_raises_error(self, email_reader):
        with pytest.raises(RuntimeError) as exc_info:
            email_reader.add_label(["1", "2"], "Processed")

        assert "Not connected to IMAP server" in str(exc_info.value)


class TestBuildSearchCriteria:
    """Test search criteria building."""

    @pytest.fixture
    def source_config(self):
        return SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
            fetch_days=7,
        )

    @pytest.fixture
    def email_reader(self, source_config):
        return EmailReader(source_config)

    def test_unread_only_with_fetch_days(self, email_reader):
        criteria = email_reader._build_search_criteria(unread_only=True)

        assert "UNSEEN" in criteria
        assert "SINCE" in criteria
        assert criteria.startswith("(")
        assert criteria.endswith(")")

    def test_all_emails_with_fetch_days(self, email_reader):
        criteria = email_reader._build_search_criteria(unread_only=False)

        assert "UNSEEN" not in criteria
        assert "SINCE" in criteria

    def test_no_fetch_days_unread_only(self):
        config = SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
            fetch_days=0,
        )
        reader = EmailReader(config)

        criteria = reader._build_search_criteria(unread_only=True)

        assert criteria == "(UNSEEN)"

    def test_no_fetch_days_all_emails(self):
        config = SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
            fetch_days=0,
        )
        reader = EmailReader(config)

        criteria = reader._build_search_criteria(unread_only=False)

        assert criteria == "ALL"


class TestEmailParsing:
    """Test email header and body parsing."""

    @pytest.fixture
    def source_config(self):
        return SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
        )

    @pytest.fixture
    def email_reader(self, source_config):
        return EmailReader(source_config)

    def test_decode_header_plain_text(self, email_reader):
        result = email_reader._decode_header("Hello World")
        assert result == "Hello World"

    def test_decode_header_none(self, email_reader):
        result = email_reader._decode_header(None)
        assert result == ""

    def test_decode_header_empty(self, email_reader):
        result = email_reader._decode_header("")
        assert result == ""

    def test_decode_header_encoded(self, email_reader):
        # RFC 2047 encoded header
        encoded = "=?utf-8?B?SGVsbG8gV29ybGQ=?="
        result = email_reader._decode_header(encoded)
        assert result == "Hello World"

    def test_parse_date_valid(self, email_reader):
        date_str = "Mon, 01 Jan 2024 12:00:00 +0000"
        result = email_reader._parse_date(date_str)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12

    def test_parse_date_none(self, email_reader):
        result = email_reader._parse_date(None)

        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_parse_date_invalid(self, email_reader):
        result = email_reader._parse_date("invalid date")

        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_get_body_plain_text(self, email_reader):
        msg = EmailMessage()
        msg.set_content("Hello, this is plain text.")

        result = email_reader._get_body(msg, "text/plain")

        assert "Hello, this is plain text." in result

    def test_get_body_html(self, email_reader):
        msg = EmailMessage()
        msg.set_content("<html><body>Hello HTML</body></html>", subtype="html")

        result = email_reader._get_body(msg, "text/html")

        assert "Hello HTML" in result

    def test_get_body_missing_type(self, email_reader):
        msg = EmailMessage()
        msg.set_content("Plain text only")

        result = email_reader._get_body(msg, "text/html")

        assert result == ""

    def test_get_body_multipart(self, email_reader):
        msg = EmailMessage()
        msg.make_mixed()
        msg.add_attachment(
            b"Plain text content", maintype="text", subtype="plain", filename=None
        )
        msg.add_attachment(
            b"<html>HTML content</html>",
            maintype="text",
            subtype="html",
            filename=None,
        )

        plain_result = email_reader._get_body(msg, "text/plain")
        html_result = email_reader._get_body(msg, "text/html")

        assert "Plain text content" in plain_result
        assert "HTML content" in html_result


class TestFetchEmails:
    """Test fetching emails from IMAP server."""

    @pytest.fixture
    def source_config(self):
        return SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
        )

    @pytest.fixture
    def email_reader(self, source_config):
        return EmailReader(source_config)

    @pytest.fixture
    def mock_imap(self):
        with patch("polyglot_pigeon.email.reader.imaplib.IMAP4_SSL") as mock:
            mock_connection = MagicMock()
            mock.return_value = mock_connection
            yield mock_connection

    @pytest.fixture
    def sample_email_bytes(self):
        msg = EmailMessage()
        msg["Subject"] = "Test Newsletter"
        msg["From"] = "sender@example.com"
        msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        msg.set_content("This is the newsletter content.")
        return msg.as_bytes()

    def test_fetch_emails_success(self, email_reader, mock_imap, sample_email_bytes):
        email_reader._connection = mock_imap
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.search.return_value = ("OK", [b"1 2"])
        mock_imap.fetch.return_value = ("OK", [(b"1", sample_email_bytes)])

        emails = email_reader.fetch_emails()

        assert len(emails) == 2
        mock_imap.select.assert_called_once_with("INBOX")

    def test_fetch_emails_custom_folder(
        self, email_reader, mock_imap, sample_email_bytes
    ):
        email_reader._connection = mock_imap
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.search.return_value = ("OK", [b"1"])
        mock_imap.fetch.return_value = ("OK", [(b"1", sample_email_bytes)])

        email_reader.fetch_emails(folder="Newsletters")

        mock_imap.select.assert_called_once_with("Newsletters")

    def test_fetch_emails_search_fails(self, email_reader, mock_imap):
        email_reader._connection = mock_imap
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.search.return_value = ("NO", [b""])

        emails = email_reader.fetch_emails()

        assert emails == []

    def test_fetch_emails_empty_result(self, email_reader, mock_imap):
        email_reader._connection = mock_imap
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.search.return_value = ("OK", [b""])

        emails = email_reader.fetch_emails()

        assert emails == []


class TestMarkAsReadAndLabel:
    """Test marking emails and adding labels."""

    @pytest.fixture
    def source_config(self):
        return SourceEmailConfig(
            address="test@example.com",
            app_password="test_password",
        )

    @pytest.fixture
    def email_reader(self, source_config):
        return EmailReader(source_config)

    @pytest.fixture
    def mock_imap(self):
        with patch("polyglot_pigeon.email.reader.imaplib.IMAP4_SSL") as mock:
            mock_connection = MagicMock()
            mock.return_value = mock_connection
            yield mock_connection

    def test_mark_as_read(self, email_reader, mock_imap):
        email_reader._connection = mock_imap

        email_reader.mark_as_read(["1", "2", "3"])

        assert mock_imap.store.call_count == 3
        mock_imap.store.assert_any_call(b"1", "+FLAGS", "\\Seen")
        mock_imap.store.assert_any_call(b"2", "+FLAGS", "\\Seen")
        mock_imap.store.assert_any_call(b"3", "+FLAGS", "\\Seen")

    def test_add_label(self, email_reader, mock_imap):
        email_reader._connection = mock_imap

        email_reader.add_label(["1", "2"], "Processed")

        assert mock_imap.store.call_count == 2
        mock_imap.store.assert_any_call(b"1", "+X-GM-LABELS", '"Processed"')
        mock_imap.store.assert_any_call(b"2", "+X-GM-LABELS", '"Processed"')


class TestEmailModel:
    """Test Email Pydantic model."""

    def test_email_model_creation(self):
        email = Email(
            uid="123",
            subject="Test Subject",
            sender="sender@example.com",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            body_text="Hello World",
            body_html="<p>Hello World</p>",
        )

        assert email.uid == "123"
        assert email.subject == "Test Subject"
        assert email.sender == "sender@example.com"
        assert email.body_text == "Hello World"
        assert email.body_html == "<p>Hello World</p>"

    def test_email_model_optional_html(self):
        email = Email(
            uid="123",
            subject="Test",
            sender="test@example.com",
            date=datetime.now(timezone.utc),
            body_text="Plain text only",
        )

        assert email.body_html is None

    def test_email_model_serialization(self):
        email = Email(
            uid="123",
            subject="Test",
            sender="test@example.com",
            date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            body_text="Content",
        )

        data = email.model_dump()

        assert data["uid"] == "123"
        assert data["subject"] == "Test"
        assert "date" in data
