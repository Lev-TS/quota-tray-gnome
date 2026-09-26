import contextlib
import base64
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
                with patch.object(quota, "codex_usage", side_effect=codex), \
                     patch.object(quota, "claude_usage", return_value=[{"name": "weekly", "used": 42, "reset": None}]), \
                     patch.object(quota, "codex_email", return_value="codex@example.com"), \
                     patch.object(quota, "claude_email", return_value="claude@example.com"):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        quota.poll()
                accounts = json.loads(output.getvalue())["accounts"]
                self.assertEqual([a["label"] for a in accounts], ["Personal", "Work", "Personal", "Work"])
                self.assertEqual(accounts[0]["windows"][0]["used"], 17)
                self.assertEqual(accounts[0]["email"], "codex@example.com")
                self.assertEqual(accounts[1]["error"], "Expired login")
                self.assertEqual(accounts[2]["windows"][0]["used"], 42)
                self.assertEqual(accounts[2]["email"], "claude@example.com")
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
            self.assertEqual(windows[0]["resetAt"], 1790445600)
            self.assertEqual(fetch.call_args.args[0].full_url, "https://api.anthropic.com/api/oauth/usage")

    def test_reset_timestamp_accepts_codex_epoch_and_claude_iso(self):
        self.assertEqual(quota.reset_timestamp(1790445600), 1790445600)
        self.assertEqual(quota.reset_timestamp("2026-09-26T18:00:00Z"), 1790445600)
        self.assertIsNone(quota.reset_timestamp("not a date"))

    def test_invalid_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "accounts.json"
            path.write_text('{"provider":"codex"}')
            with patch.object(quota, "CONFIG", path):
                with self.assertRaisesRegex(ValueError, "JSON array"):
                    quota.read_accounts()

    def test_codex_email_comes_from_the_selected_login_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            for folder, email in ((first, "first@example.com"), (second, "second@example.com")):
                folder.mkdir()
                claim = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
                (folder / "auth.json").write_text(json.dumps({"tokens": {"id_token": f"header.{claim}.signature"}}))
            self.assertEqual(quota.codex_email(first), "first@example.com")
            self.assertEqual(quota.codex_email(second), "second@example.com")

    def test_claude_email_uses_the_selected_config_directory(self):
        completed = type("Completed", (), {"stdout": '{"loggedIn":true,"email":"work@example.com"}'})()
        with patch.object(quota.subprocess, "run", return_value=completed) as command:
            self.assertEqual(quota.claude_email("/claude-work"), "work@example.com")
        self.assertEqual(command.call_args.kwargs["env"]["CLAUDE_CONFIG_DIR"], "/claude-work")

    def test_manual_email_labels_a_custom_account(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(quota, "CONFIG", Path(directory) / "accounts.json"):
                quota.write_accounts([{"provider": "claude", "label": "Work", "path": directory,
                                       "email": "work@example.com"}])
                with patch.object(quota, "claude_email", return_value=None), patch.object(
                    quota, "claude_usage", return_value=[]
                ):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        quota.poll()
                self.assertEqual(json.loads(output.getvalue())["accounts"][0]["email"], "work@example.com")


if __name__ == "__main__":
    unittest.main()
