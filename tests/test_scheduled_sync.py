import unittest
from datetime import datetime, timezone, timedelta

from OutlookAgent.scheduled_sync import should_run_now


class ScheduledSyncTests(unittest.TestCase):
    def test_should_run_now_inside_window(self):
        now = datetime(2026, 7, 10, 8, 45, tzinfo=timezone(timedelta(hours=-5)))
        self.assertTrue(should_run_now(now))

    def test_should_run_now_outside_window_hour(self):
        now = datetime(2026, 7, 10, 14, 45, tzinfo=timezone(timedelta(hours=-5)))
        self.assertFalse(should_run_now(now))

    def test_should_run_now_outside_window_minute(self):
        now = datetime(2026, 7, 10, 8, 30, tzinfo=timezone(timedelta(hours=-5)))
        self.assertFalse(should_run_now(now))


if __name__ == "__main__":
    unittest.main()
