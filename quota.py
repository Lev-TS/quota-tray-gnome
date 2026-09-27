#!/usr/bin/env python3
"""Read quota for independently logged-in Codex and Claude Code accounts."""

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "quota-tray" / "accounts.json"
PROVIDERS = ("codex", "claude")


def read_accounts():
    if not CONFIG.exists():
        return []
    data = json.loads(CONFIG.read_text())
    if not isinstance(data, list):
        raise ValueError("Account config must be a JSON array")
    accounts = []
    for item in data:
        if not isinstance(item, dict) or item.get("provider") not in PROVIDERS:
            raise ValueError("Each account needs provider codex or claude")
        label = item.get("label")
        path = item.get("path")
        if not isinstance(label, str) or not label.strip() or not isinstance(path, str) or not path:
            raise ValueError("Each account needs a label and path")
        account = {"provider": item["provider"], "label": label.strip(), "path": str(Path(path).expanduser())}
        email = item.get("email")
        if email is not None:
            if not isinstance(email, str) or "@" not in email:
                raise ValueError("An account email must be a valid email address")
            account["email"] = email
        plan = item.get("plan")
        if plan is not None:
            if not isinstance(plan, str) or not plan.strip():
                raise ValueError("An account plan must be a non-empty string")
            account["plan"] = plan.strip()
        accounts.append(account)
    return accounts


def write_accounts(accounts):
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(accounts, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(CONFIG)


def reset_timestamp(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (AttributeError, OverflowError, ValueError, OSError, TypeError):
        return None


def reset_time(value):
    timestamp = reset_timestamp(value)
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp).astimezone().strftime("%a %H:%M")
    except (OverflowError, ValueError, OSError):
        return None


def percentage(value):
    return max(0.0, min(100.0, float(value)))


def codex_email(path):
    """Read the email claim from this CLI account's cached identity token."""
    try:
        token = json.loads((Path(path) / "auth.json").read_text())["tokens"]["id_token"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        email = claims.get("email")
        return email if isinstance(email, str) and "@" in email else None
    except (OSError, ValueError, KeyError, IndexError, binascii.Error):
        return None


def claude_email(path):
    """Ask Claude Code which account is signed into this config directory."""
    env = os.environ.copy()
    if Path(path).resolve() == (Path.home() / ".claude").resolve():
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = path
    claude = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
    try:
        status = subprocess.run([claude, "auth", "status", "--json"], env=env,
                                capture_output=True, text=True, timeout=8, check=True)
        data = json.loads(status.stdout)
        email = data.get("email")
        if data.get("loggedIn") and isinstance(email, str) and "@" in email:
            return email
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def codex_usage(path):
    if not (Path(path) / "auth.json").is_file():
        raise ValueError("No auth.json. Sign in with CODEX_HOME set to this folder")
    env = os.environ.copy()
    env["CODEX_HOME"] = path
    codex = shutil.which("codex") or str(Path.home() / ".local" / "bin" / "codex")
    process = subprocess.Popen(
        [codex, "app-server", "--stdio"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    try:
        requests = [
            {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "quota-tray", "version": "1"}}},
            {"method": "initialized"},
            {"id": 2, "method": "account/rateLimits/read", "params": {"excludeResetCreditDetails": True}},
        ]
        for request in requests:
            process.stdin.write((json.dumps(request) + "\n").encode())
        process.stdin.flush()
        deadline = time.monotonic() + 20
        response = None
        buffer = b""
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], max(0, deadline - time.monotonic()))
            if not ready:
                break
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if message.get("id") == 2:
                    response = message
                    break
            if response is not None:
                break
        if response is None:
            raise TimeoutError("Codex did not return usage")
        if "error" in response:
            raise ValueError(response["error"].get("message", "Codex usage request failed"))
        result = response["result"]
        snapshots = result.get("rateLimitsByLimitId") or {}
        if not snapshots:
            snapshots = {"Codex": result.get("rateLimits", {})}
        windows = []
        for name, snapshot in snapshots.items():
            for key in ("primary", "secondary"):
                window = snapshot.get(key)
                if window and window.get("usedPercent") is not None:
                    duration = window.get("windowDurationMins")
                    if isinstance(duration, int) and duration >= 10080:
                        window_name = "weekly"
                    elif isinstance(duration, int) and duration >= 60:
                        window_name = f"{duration // 60}h"
                    else:
                        window_name = key
                    windows.append({"name": f"{snapshot.get('limitName') or name} {window_name}",
                                    "used": percentage(window["usedPercent"]),
                                    "reset": reset_time(window.get("resetsAt")),
                                    "resetAt": reset_timestamp(window.get("resetsAt"))})
        return windows
    finally:
        process.terminate()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


def claude_usage(path):
    credentials_path = Path(path) / ".credentials.json"
    if not credentials_path.is_file():
        raise ValueError("No .credentials.json. Sign in with CLAUDE_CONFIG_DIR set to this folder")
    credentials = json.loads(credentials_path.read_text()).get("claudeAiOauth", {})
    token = credentials.get("accessToken")
    if not token:
        raise ValueError("Claude Code login has no access token")
    expiry = credentials.get("expiresAt")
    if expiry and int(expiry) / 1000 < time.time():
        raise ValueError("Claude token expired. Open Claude Code with this config folder to refresh it")
    request = Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json", "User-Agent": "quota-tray/1"})
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code == 429:
            raise ValueError("Claude usage is rate limited. Try again later") from error
        raise ValueError(f"Claude usage returned HTTP {error.code}") from error
    except URLError as error:
        raise ValueError(f"Claude usage network error: {error.reason}") from error
    windows = []
    for key, label in (("five_hour", "5h"), ("seven_day", "weekly")):
        window = data.get(key)
        if isinstance(window, dict) and window.get("utilization") is not None:
            windows.append({"name": label, "used": percentage(window["utilization"]),
                            "reset": reset_time(window.get("resets_at")),
                            "resetAt": reset_timestamp(window.get("resets_at"))})
    return windows


def poll():
    accounts = read_accounts()
    result = []
    for account in accounts:
        entry = {"provider": account["provider"], "label": account["label"]}
        if account.get("plan"):
            entry["plan"] = account["plan"]
        email = account.get("email") or (codex_email if account["provider"] == "codex" else claude_email)(account["path"])
        if email:
            entry["email"] = email
        try:
            entry["windows"] = (codex_usage if account["provider"] == "codex" else claude_usage)(account["path"])
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as error:
            entry["error"] = str(error)
        result.append(entry)
    print(json.dumps({"accounts": result}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("poll")
    subcommands.add_parser("list")
    add = subcommands.add_parser("add")
    add.add_argument("provider", choices=PROVIDERS)
    add.add_argument("label")
    add.add_argument("path", help="CLI config directory containing auth.json or .credentials.json")
    add.add_argument("--email", help="Optional display email when the CLI does not report it")
    add.add_argument("--plan", help="Optional subscription plan label to show on the account card")
    remove = subcommands.add_parser("remove")
    remove.add_argument("provider", choices=PROVIDERS)
    remove.add_argument("label")
    args = parser.parse_args()
    if args.command == "poll":
        poll()
        return
    accounts = read_accounts()
    if args.command == "list":
        for account in accounts:
            suffix = f"\t{account['plan']}" if account.get("plan") else ""
            print(f"{account['provider']}\t{account['label']}\t{account['path']}{suffix}")
    elif args.command == "add":
        path = str(Path(args.path).expanduser().resolve())
        if not Path(path).is_dir():
            parser.error(f"Not a directory: {path}")
        if any(a["provider"] == args.provider and a["label"] == args.label for a in accounts):
            parser.error("That provider and label already exist")
        account = {"provider": args.provider, "label": args.label, "path": path}
        if args.email:
            if "@" not in args.email:
                parser.error("Email must contain @")
            account["email"] = args.email
        if args.plan is not None:
            if not args.plan.strip():
                parser.error("Plan must not be empty")
            account["plan"] = args.plan.strip()
        accounts.append(account)
        write_accounts(accounts)
    else:
        updated = [a for a in accounts if (a["provider"], a["label"]) != (args.provider, args.label)]
        if len(updated) == len(accounts):
            parser.error("Account not found")
        write_accounts(updated)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"quota-tray: {error}", file=sys.stderr)
        sys.exit(1)
