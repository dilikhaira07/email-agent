import unittest

from OutlookAgent.sync_state import filter_new_items, meeting_key, remember_items, task_key


class SyncStateTests(unittest.TestCase):
    def test_task_key_is_stable_across_whitespace_and_case(self):
        a = {
            "title": "Reply To Vendor",
            "action": "Send confirmation",
            "body": "Need to confirm install window.",
            "urgent": True,
            "due_date": "2026-03-28T00:00:00",
        }
        b = {
            "title": "  reply to vendor ",
            "action": "send confirmation",
            "body": "Need to confirm   install window.",
            "urgent": True,
            "due_date": "2026-03-28T00:00:00",
        }
        self.assertEqual(task_key(a), task_key(b))

    def test_filter_new_items_skips_existing_and_duplicates_in_run(self):
        item = {
            "title": "Reply",
            "action": "Reply now",
            "body": "Context",
            "urgent": False,
            "due_date": None,
        }
        state = {"tasks": {task_key(item): "2026-03-28T00:00:00"}, "meetings": {}}
        items = [item, dict(item), {**item, "title": "New title"}]

        fresh_items, fresh_keys = filter_new_items(items, "tasks", state, task_key)

        self.assertEqual(len(fresh_items), 1)
        self.assertEqual(len(fresh_keys), 1)
        self.assertEqual(fresh_items[0]["title"], "New title")

    def test_remember_items_adds_keys(self):
        state = {"tasks": {}, "meetings": {}}
        key = meeting_key(
            {
                "title": "Weekly Check-In",
                "date": "2026-03-30",
                "attendees": "A, B",
                "agenda": "Status",
                "status": "Scheduled",
                "link": None,
            }
        )

        remember_items(state, "meetings", [key])

        self.assertIn(key, state["meetings"])


if __name__ == "__main__":
    unittest.main()
