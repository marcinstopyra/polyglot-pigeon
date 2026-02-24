from datetime import datetime

from polyglot_pigeon.content import ContentCleaner
from polyglot_pigeon.models.models import Email

# Enough padding to push any footer trigger past the 60% tail threshold.
_PAD = "Article content fills space. " * 6


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

    def test_body_text_containing_html_is_stripped(self):
        cleaner = ContentCleaner()
        # Some senders put raw HTML in the text/plain MIME part
        email = _make_email(
            body_text="<!DOCTYPE html><html><body><p>Article</p></body></html>",
            body_html=None,
        )

        results = cleaner.clean([email])

        assert "Article" in results[0].body
        assert "<p>" not in results[0].body
        assert "<!DOCTYPE" not in results[0].body

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

    def test_strips_hidden_preheader_span(self):
        cleaner = ContentCleaner()
        html = (
            '<span style="display:none">Preheader preview text</span>'
            "<p>Actual article content</p>"
        )
        email = _make_email(body_text="", body_html=html)

        results = cleaner.clean([email])

        assert "Actual article content" in results[0].body
        assert "Preheader preview text" not in results[0].body

    def test_removes_unsubscribe_boilerplate(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text=f"{_PAD}\nUnsubscribe from this list.")

        results = cleaner.clean([email])

        assert "Article content" in results[0].body
        assert "Unsubscribe" not in results[0].body

    def test_unsubscribe_early_in_email_is_not_cut(self):
        # A survey CTA near the top should NOT wipe the rest of the email
        cleaner = ContentCleaner()
        email = _make_email(
            body_text=f"Please fill our survey or unsubscribe here.\n{_PAD}"
        )

        results = cleaner.clean([email])

        assert "Article content" in results[0].body

    def test_removes_view_in_browser(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="Article text.\nView this email in your browser")

        results = cleaner.clean([email])

        assert "Article text" in results[0].body
        assert "View this email" not in results[0].body

    def test_removes_copyright_footer(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text=f"{_PAD}\n© 2025 Company Inc. All rights reserved."
        )

        results = cleaner.clean([email])

        assert "Article content" in results[0].body
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
        # 5 newlines → collapsed to max 2 blank lines (3 newlines)
        email = _make_email(body_text="Line one.\n\n\n\n\nLine two.")

        results = cleaner.clean([email])

        assert "Line one.\n\n\nLine two." in results[0].body

    def test_whitespace_only_lines_are_collapsed(self):
        cleaner = ContentCleaner()
        # Lines containing only spaces should be treated as blank lines
        email = _make_email(body_text="Line one.\n   \n   \n   \nLine two.")

        results = cleaner.clean([email])

        assert "Line one." in results[0].body
        assert "Line two." in results[0].body
        # Should be at most 2 blank lines between them
        assert "\n\n\n\n" not in results[0].body

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

    def test_strips_tracking_urls(self):
        cleaner = ContentCleaner()
        text = "Check this out https://list-manage.com/track/click?u=abc&id=xyz for more info."
        email = _make_email(body_text=text)

        results = cleaner.clean([email])

        assert "list-manage.com" not in results[0].body
        assert "Check this out" in results[0].body
        assert "for more info" in results[0].body

    def test_strips_inline_parenthesized_urls(self):
        cleaner = ContentCleaner()
        text = "Click here (https://example.com/newsletter?utm_source=test&mc_eid=UNIQID) to subscribe."
        email = _make_email(body_text=text)

        results = cleaner.clean([email])

        assert "Click here" in results[0].body
        assert "to subscribe" in results[0].body
        assert "https://example.com" not in results[0].body

    def test_strips_invisible_unicode(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="Real\u200bcontent\u034fhere")

        results = cleaner.clean([email])

        assert results[0].body == "Realcontenthere"

    def test_removes_duplicate_consecutive_lines(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="Photo caption\nPhoto caption\nActual article text"
        )

        results = cleaner.clean([email])

        assert results[0].body.count("Photo caption") == 1
        assert "Actual article text" in results[0].body

    def test_strips_promotional_footer_become_member(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text=f"{_PAD}\nBecome a member to access premium articles.")

        results = cleaner.clean([email])

        assert "Article content" in results[0].body
        assert "Become a member" not in results[0].body

    def test_strips_promotional_footer_explore_newsletters(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text=f"{_PAD}\nExplore other newsletters from our team.\nSign up now!"
        )

        results = cleaner.clean([email])

        assert "Article content" in results[0].body
        assert "Explore other newsletters" not in results[0].body

    def test_strips_bare_urls(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="Read more:\nhttps://example.com/some/long/article/path\nMore content below."
        )

        results = cleaner.clean([email])

        assert "Read more" in results[0].body
        assert "https://example.com" not in results[0].body
        assert "More content below" in results[0].body

    def test_strips_ui_label_advertisement(self):
        cleaner = ContentCleaner()
        email = _make_email(body_text="Article text.\nADVERTISEMENT\nMore article text.")

        results = cleaner.clean([email])

        assert "Article text" in results[0].body
        assert "More article text" in results[0].body
        assert "ADVERTISEMENT" not in results[0].body

    def test_strips_sponsor_line(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="News content.\nPlease support our sponsors!\nMore news."
        )

        results = cleaner.clean([email])

        assert "News content" in results[0].body
        assert "More news" in results[0].body
        assert "support our sponsors" not in results[0].body

    def test_strips_in_partnership_with(self):
        cleaner = ContentCleaner()
        email = _make_email(
            body_text="News section.\nIn partnership with Acme Corp\nMore news."
        )

        results = cleaner.clean([email])

        assert "News section" in results[0].body
        assert "More news" in results[0].body
        assert "In partnership with" not in results[0].body

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
