import unittest
from email.message import EmailMessage

from OutlookAgent.email_normalize import build_preview, extract_urls, html_to_text


class EmailNormalizeTests(unittest.TestCase):
    def test_prefers_plain_text_and_keeps_link(self):
        msg = EmailMessage()
        msg.set_content("Meeting at 3pm https://teams.example.com/abc")
        msg.add_alternative("<p>Ignore html</p>", subtype="html")

        preview = build_preview(msg, max_chars=200)

        self.assertIn("Meeting at 3pm", preview)
        self.assertIn("https://teams.example.com/abc", preview)

    def test_falls_back_to_html_text(self):
        msg = EmailMessage()
        msg.add_alternative(
            "<html><body><p>Join the call</p><a href='https://zoom.example.com/j/123'>Zoom</a></body></html>",
            subtype="html",
        )

        preview = build_preview(msg, max_chars=200)

        self.assertIn("Join the call", preview)
        self.assertIn("https://zoom.example.com/j/123", preview)

    def test_html_to_text_strips_tags(self):
        text = html_to_text("<div>Hello <b>world</b></div>")
        self.assertEqual(text, "Hello world")

    def test_extract_urls_deduplicates_and_limits(self):
        urls = extract_urls(
            "a https://a.example/x b https://a.example/x c https://b.example/y d https://c.example/z e https://d.example/q"
        )
        self.assertEqual(
            urls,
            [
                "https://a.example/x",
                "https://b.example/y",
                "https://c.example/z",
            ],
        )


if __name__ == "__main__":
    unittest.main()
