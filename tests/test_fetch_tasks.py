import unittest

from OutlookAgent.fetch_tasks import _coerce_list_of_dicts, _parse_json_response


class FetchTasksHelpersTests(unittest.TestCase):
    def test_parse_json_response_accepts_code_fence_wrapped_json(self):
        raw = """```json
{"summary_markdown":"x","tasks":[],"meetings":[]}
```"""

        parsed = _parse_json_response(raw, "payload")

        self.assertEqual(parsed["summary_markdown"], "x")
        self.assertEqual(parsed["tasks"], [])
        self.assertEqual(parsed["meetings"], [])

    def test_parse_json_response_raises_on_invalid_json(self):
        with self.assertRaises(RuntimeError):
            _parse_json_response("{bad json", "payload")

    def test_coerce_list_of_dicts_filters_non_dict_entries(self):
        value = [{"title": "ok"}, "bad", 1, {"title": "still ok"}]

        result = _coerce_list_of_dicts(value)

        self.assertEqual(result, [{"title": "ok"}, {"title": "still ok"}])


if __name__ == "__main__":
    unittest.main()
