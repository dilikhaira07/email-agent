import unittest

from OutlookAgent.telegram_notify import build_summary


class TelegramNotifyTests(unittest.TestCase):
    def test_build_summary_handles_empty_payload(self):
        text = build_summary([], [])
        self.assertIn("New items:</b> 0", text)
        self.assertIn("No new tasks or meetings found.", text)

    def test_build_summary_escapes_html_sensitive_content(self):
        tasks = [
            {
                "title": 'Fix <router> & confirm "cutover"',
                "action": "Reply <now> & confirm",
                "urgent": True,
                "due_date": "2026-03-28T00:00:00",
            }
        ]
        meetings = [
            {
                "title": "Vendor <Check-In>",
                "date": "2026-03-30",
                "status": "Scheduled",
                "agenda": "Discuss <scope> & risks",
                "link": "https://zoom.example.com/j/123?a=1&b=2",
            }
        ]

        text = build_summary(tasks, meetings)

        self.assertIn("Fix &lt;router&gt; &amp; confirm", text)
        self.assertIn("Reply &lt;now&gt; &amp; confirm", text)
        self.assertIn("Vendor &lt;Check-In&gt;", text)
        self.assertIn("https://zoom.example.com/j/123?a=1&amp;b=2", text)

    def test_build_summary_includes_structured_sections(self):
        tasks = [
            {
                "title": "Reply to vendor",
                "action": "Send approval",
                "urgent": True,
                "due_date": "2026-03-28T00:00:00",
            },
            {
                "title": "Review quote",
                "action": "Check pricing",
                "urgent": False,
                "due_date": None,
            },
        ]
        meetings = [
            {
                "title": "Weekly sync",
                "date": "2026-03-30",
                "status": "Scheduled",
                "agenda": "Status update",
                "link": None,
            }
        ]

        text = build_summary(tasks, meetings)

        self.assertIn("URGENT (1)", text)
        self.assertIn("THIS WEEK (1)", text)
        self.assertIn("MEETINGS (1)", text)
        self.assertIn("Action: Send approval", text)
        self.assertIn("Agenda: Status update", text)


if __name__ == "__main__":
    unittest.main()
