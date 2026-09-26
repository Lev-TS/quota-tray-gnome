# Quota Tray

A GNOME Shell 50 top bar extension for multiple Codex and Claude Code subscriptions. Each account has its own CLI config directory. The top bar shows the percentage left in the most depleted window for every account. Click it to see each window and its reset time.

Quota Tray reads Codex usage through `codex app-server` and Claude usage through the Claude Code OAuth usage endpoint. The account list stores labels and config paths only. It does not copy tokens or change your active CLI account. Codex may refresh its own login while the app server runs. Claude tokens refresh when you use Claude Code in that account's config directory.

## Install

```sh
ln -s /home/levan/repos/quota-tray-gnome ~/.local/share/gnome-shell/extensions/quota-tray@levan.local
```

Log out and back in, then run `gnome-extensions enable quota-tray@levan.local`. GNOME on Wayland loads a newly installed extension after a new login.

## Add accounts

```sh
python3 /home/levan/repos/quota-tray-gnome/quota.py add codex Personal ~/.codex
python3 /home/levan/repos/quota-tray-gnome/quota.py add claude Personal ~/.claude
```

For more subscriptions, sign in with separate CLI config directories and add each directory:

```sh
CODEX_HOME="$HOME/.codex-work" codex login
CLAUDE_CONFIG_DIR="$HOME/.claude-work" claude auth login
python3 /home/levan/repos/quota-tray-gnome/quota.py add codex Work ~/.codex-work
python3 /home/levan/repos/quota-tray-gnome/quota.py add claude Work ~/.claude-work
```

Run `python3 quota.py list` to see configured accounts and `python3 quota.py remove codex Work` to remove one from the indicator. `python3 quota.py poll` prints the same data the extension displays. Account settings live in `~/.config/quota-tray/accounts.json`.

The Codex login must use file-based credentials. In its `config.toml`, set `cli_auth_credentials_store = "file"` before logging in if that account otherwise uses the OS keyring. API-key accounts do not have subscription quota windows.

Claude usage requests may receive a 429 response. Quota Tray then shows an error for that account and tries again at the next refresh. It polls every five minutes. Opening the menu refreshes stale data, and the menu also has a manual refresh action.

## Package

To make a standalone ZIP that includes the reader and icon, run:

```sh
gnome-extensions pack --extra-source=quota.py --extra-source=quota-symbolic.svg .
```
