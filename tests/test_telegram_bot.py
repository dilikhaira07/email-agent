import unittest

from OutlookAgent.telegram_bot import (
    _command_name,
    HELP_TEXT,
    _build_task_keyboard,
    _format_task_list,
    _parse_callback_data,
    _parse_index_arg,
    _task_list_payload,
    _with_command_footer,
)


class TelegramBotTests(unittest.TestCase):
    def test_parse_index_arg(self):
        self.assertEqual(_parse_index_arg("/done 3"), 3)
        self.assertIsNone(_parse_index_arg("/done"))
        self.assertIsNone(_parse_index_arg("/done abc"))

    def test_format_task_list_structures_output(self):
        text = _format_task_list([
            {
                "id": "page-1",
                "title": "Reply to vendor",
                "priority": "Urgent",
                "status": "To Do",
                "due_date": "2026-03-28",
            }
        ])
        self.assertIn("Open Tasks (1)", text)
        self.assertIn("1. Reply to vendor", text)
        self.assertIn("Priority: Urgent", text)
        self.assertIn("Status: To Do", text)
        self.assertIn("Due: 2026-03-28", text)

    def test_format_task_list_handles_empty(self):
        text = _format_task_list([])
        self.assertIn("BOT BUILD: TASK-COMMANDS-V3", text)
        self.assertIn("No open tasks.", text)

    def test_build_task_keyboard_builds_button_rows(self):
        keyboard = _build_task_keyboard([
            {"id": "page-1", "title": "Reply"},
            {"id": "page-2", "title": "Review"},
        ])
        self.assertEqual(len(keyboard["inline_keyboard"]), 2)
        self.assertEqual(keyboard["inline_keyboard"][0][0]["callback_data"], "done:page-1")
        self.assertEqual(keyboard["inline_keyboard"][0][1]["callback_data"], "delete:page-1")

    def test_parse_callback_data(self):
        self.assertEqual(_parse_callback_data("done:page-1"), ("done", "page-1"))
        self.assertEqual(_parse_callback_data("delete:page-2"), ("delete", "page-2"))
        self.assertEqual(_parse_callback_data("bad:data"), (None, None))
        self.assertEqual(_parse_callback_data("missing"), (None, None))

    def test_with_command_footer_appends_once(self):
        text = _with_command_footer("Ready.")
        self.assertIn("Commands:", text)
        self.assertEqual(_with_command_footer(text), text)

    def test_task_list_payload_includes_keyboard_when_tasks_exist(self):
        payload = _task_list_payload([
            {"id": "page-1", "title": "Reply", "priority": "Urgent", "status": "To Do", "due_date": None}
        ])
        self.assertIn("reply_markup", payload)
        self.assertEqual(payload["parse_mode"], "HTML")

    def test_help_text_mentions_task_alias(self):
        self.assertIn("/tasks or /task", HELP_TEXT)

    def test_command_name_strips_bot_suffix(self):
        self.assertEqual(_command_name("/task@TestBot"), "/task")
        self.assertEqual(_command_name("/tasks@TestBot something"), "/tasks")


if __name__ == "__main__":
    unittest.main()
