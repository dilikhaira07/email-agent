import unittest
from unittest.mock import patch

from OutlookAgent import notion_tasks


class NotionTasksTests(unittest.TestCase):
    def test_task_exists_matches_title_and_due_date(self):
        task = {
            "title": "Reply to Vendor",
            "action": "Reply today",
            "body": "Need to confirm schedule.",
            "urgent": True,
            "due_date": "2026-03-28T00:00:00",
        }
        page = {
            "properties": {
                "Task": {
                    "title": [{"plain_text": "🔴 Reply to Vendor"}],
                },
                "Due Date": {
                    "date": {"start": "2026-03-28"},
                },
            }
        }

        with patch.object(notion_tasks, "_query_database", return_value=[page]):
            self.assertTrue(notion_tasks.task_exists(task))

    def test_task_exists_rejects_same_title_with_different_due_date(self):
        task = {
            "title": "Reply to Vendor",
            "action": "Reply today",
            "body": "Need to confirm schedule.",
            "urgent": True,
            "due_date": "2026-03-28T00:00:00",
        }
        page = {
            "properties": {
                "Task": {
                    "title": [{"plain_text": "🔴 Reply to Vendor"}],
                },
                "Due Date": {
                    "date": {"start": "2026-03-29"},
                },
            }
        }

        with patch.object(notion_tasks, "_query_database", return_value=[page]):
            self.assertFalse(notion_tasks.task_exists(task))

    def test_meeting_exists_matches_title_and_date(self):
        meeting = {
            "title": "Weekly Check-In",
            "date": "2026-03-30",
            "attendees": "A, B",
            "agenda": "Status update",
            "status": "Scheduled",
            "link": None,
        }
        page = {
            "properties": {
                "Meeting": {
                    "title": [{"plain_text": "🟦 Weekly Check-In"}],
                },
                "Date": {
                    "date": {"start": "2026-03-30"},
                },
            }
        }

        with patch.object(notion_tasks, "_query_database", return_value=[page]):
            self.assertTrue(notion_tasks.meeting_exists(meeting))

    def test_meeting_exists_rejects_same_title_with_different_date(self):
        meeting = {
            "title": "Weekly Check-In",
            "date": "2026-03-30",
            "attendees": "A, B",
            "agenda": "Status update",
            "status": "Scheduled",
            "link": None,
        }
        page = {
            "properties": {
                "Meeting": {
                    "title": [{"plain_text": "🟦 Weekly Check-In"}],
                },
                "Date": {
                    "date": {"start": "2026-04-01"},
                },
            }
        }

        with patch.object(notion_tasks, "_query_database", return_value=[page]):
            self.assertFalse(notion_tasks.meeting_exists(meeting))


if __name__ == "__main__":
    unittest.main()
