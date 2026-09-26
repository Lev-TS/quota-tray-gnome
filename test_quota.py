import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import quota


class QuotaTests(unittest.TestCase):
    def test_multiple_accounts_stay_separate_and_one_failure_does_not_hide_others(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(quota, "CONFIG", Path(directory) / "accounts.json"):
                quota.write_accounts([
                    {"provider": "codex", "label": "Personal", "path": "/codex-one"},
                    {"provider": "codex", "label": "Work", "path": "/codex-two"},
                    {"provider": "claude", "label": "Personal", "path": "/claude-one"},
                    {"provider": "claude", "label": "Work", "path": "/claude-two"},
                ])
                def codex(path):
                    if path == "/codex-two":
                        raise ValueError("Expired login")
                    return [{"name": "5h", "used": 17, "reset": None}]
                with patch.object(quota, "codex_usage", side_effect=codex), patch.object(
                    quota, "claude_usage", return_value=[{"name": "weekly", "used": 42, "reset": None}]
                ):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        quota.poll()
                accounts = json.loads(output.getvalue())["accounts"]
                self.assertEqual([a["label"] for a in accounts], ["Personal", "Work", "Personal", "Work"])
                self.assertEqual(accounts[0]["windows"][0]["used"], 17)
                self.assertEqual(accounts[1]["error"], "Expired login")
                self.assertEqual(accounts[2]["windows"][0]["used"], 42)
                self.assertEqual(accounts[3]["windows"][0]["used"], 42)

    def test_claude_usage_parses_windows_and_reset_times(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = {"claudeAiOauth": {"accessToken": "fixture-token"}}
            (Path(directory) / ".credentials.json").write_text(json.dumps(credentials))
            response = io.BytesIO(json.dumps({
                "five_hour": {"utilization": 12.5, "resets_at": "2026-09-26T18:00:00Z"},
                "seven_day": {"utilization": 31, "resets_at": "2026-09-29T18:00:00Z"},
            }).encode())
            with patch.object(quota, "urlopen", return_value=response) as fetch:
                windows = quota.claude_usage(directory)
            self.assertEqual([w["name"] for w in windows], ["5h", "weekly"])
            self.assertEqual([w["used"] for w in windows], [12.5, 31])
            self.assertIsNotNone(windows[0]["reset"])
            self.assertEqual(fetch.call_args.args[0].full_url, "https://api.anthropic.com/api/oauth/usage")

    def test_invalid_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            path.write_text('{"provider":"codex"}')
            with patch.object(quota, "CONFIG", path):
                with self.assertRaisesRegex(ValueError, "JSON array"):
                    quota.read_accounts()


if __name__ == "__main__":
    unittest.main()
