from datetime import datetime

from polyglot_pigeon.content import ContentCleaner
from polyglot_pigeon.models.models import Email


def _make_email(
    body_text: str = "",
    body_html: str | None = None,
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
) -> Email:
    return Email(
        uid="1",
        subject=subject,
        sender=sender,
        date=datetime(2025, 1, 1),
        body_text=body_text,
        body_html=body_html,
    )


class TestContentCleaner:
    def test_prefers_body_text_over_html(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="Plain text content", body_html="<p>HTML content</p>"
        )

        results = cleaner.clean([email])

        assert len(results) == 1
        assert "Plain text content" in results[0].body

    def test_falls_back_to_html(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="", body_html="<p>HTML only content</p>")

        results = cleaner.clean([email])

        assert len(results) == 1
        assert "HTML only content" in results[0].body

    def test_strips_html_tags(self):
        cleaner = ContentCleaner()
        html = "<h1>Title</h1><p>Paragraph <b>bold</b> text</p>"
        email = _make_email(body_text="", body_html=html)

        results = cleaner.clean([email])

        assert "<h1>" not in results[0].body
        assert "<p>" not in results[0].body
        assert "Title" in results[0].body
        assert "bold" in results[0].body

    def test_strips_script_and_style(self):
        cleaner = ContentCleaner()
        html = "<p>Visible</p><script>alert('x')</script><style>.a{color:red}</style><p>Also visible</p>"
        email = _make_email(body_text="", body_html=html)

        results = cleaner.clean([email])

        assert "Visible" in results[0].body
        assert "Also visible" in results[0].body
        assert "alert" not in results[0].body
        assert "color" not in results[0].body

    def test_removes_unsubscribe_boilerplate(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="Good content here.\nUnsubscribe from this list.")

        results = cleaner.clean([email])

        assert "Good content" in results[0].body
        assert "Unsubscribe" not in results[0].body

    def test_removes_view_in_browser(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="Article text.\nView this email in your browser")

        results = cleaner.clean([email])

        assert "Article text" in results[0].body
        assert "View this email" not in results[0].body

    def test_removes_copyright_footer(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="News content.\n© 2025 Company Inc. All rights reserved."
        )

        results = cleaner.clean([email])

        assert "News content" in results[0].body
        assert "Company Inc" not in results[0].body

    def test_preserves_metadata(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="Content",
            subject="Weekly Digest",
            sender="news@example.com",
        )

        results = cleaner.clean([email])

        assert results[0].subject == "Weekly Digest"
        assert results[0].sender == "news@example.com"

    def test_skips_empty_emails(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="", body_html=None)

        results = cleaner.clean([email])

        assert len(results) == 0

    def test_normalizes_excessive_whitespace(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="Line one.\n\n\n\n\nLine two.")

        results = cleaner.clean([email])

        assert "Line one.\n\nLine two." in results[0].body

    def test_strips_figcaption(self):
        cleaner = ContentCleaner()
        html = "<p>Article text</p><figure><img src='photo.jpg'><figcaption>Photo by John</figcaption></figure><p>More text</p>"
        email = _make_email(body_text="", body_html=html)

        results = cleaner.clean([email])

        assert "Article text" in results[0].body
        assert "More text" in results[0].body
        assert "Photo by John" not in results[0].body

    def test_strips_img_alt_text(self):
        cleaner = ContentCleaner()
        html = '<p>Before</p><img src="pic.jpg" alt="A nice photo"><p>After</p>'
        email = _make_email(body_text="", body_html=html)

        results = cleaner.clean([email])

        assert "Before" in results[0].body
        assert "After" in results[0].body
        assert "nice photo" not in results[0].body

    def test_multiple_emails(self):
        cleaner = ContentCleaner()
        emails = [
            _make_email(body_text="First article", subject="Email 1"),
            _make_email(body_text="Second article", subject="Email 2"),
        ]

        results = cleaner.clean(emails)

        assert len(results) == 2
        assert results[0].subject == "Email 1"
        assert results[1].subject == "Email 2"
