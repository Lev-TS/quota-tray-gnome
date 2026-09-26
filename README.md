# Quota Tray

A GNOME Shell 50 top bar extension for multiple Codex and Claude Code subscriptions. Each account has its own CLI config directory. The top bar shows the selected provider's icon and its 5h remaining percentage. Click it to see provider cards with each account's quota windows and remaining percentage. A live reset countdown appears below each 5h meter. Weekly meters show the reset day and time. Click a card to choose which account appears in the top bar. The choice is saved in `~/.config/quota-tray/selection.json`.

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

Cards show the account email when the CLI provides it. Codex supplies it from the saved identity token. Claude may omit it for a separate config folder; add a display email yourself in that case:

```sh
python3 /home/levan/repos/quota-tray-gnome/quota.py add claude Work ~/.claude-work --email you@example.com
```

Use either Claude `add` command above, depending on whether its CLI reports the email. The email is only a display label and is stored with the account path in your local config file.

Run `python3 quota.py list` to see configured accounts and `python3 quota.py remove codex Work` to remove one from the indicator. `python3 quota.py poll` prints the same data the extension displays. Account settings live in `~/.config/quota-tray/accounts.json`.

The Codex login must use file-based credentials. In its `config.toml`, set `cli_auth_credentials_store = "file"` before logging in if that account otherwise uses the OS keyring. API-key accounts do not have subscription quota windows.

Claude usage requests may receive a 429 response. Quota Tray then shows an error for that account and tries again at the next refresh. It polls every five minutes. The 5h countdown updates every 30 seconds without polling the providers. Opening the menu refreshes stale data, and the menu also has a manual refresh action.

## Package

To make a standalone ZIP that includes the reader and icons, run:

```sh
gnome-extensions pack --extra-source=quota.py --extra-source=meter.js --extra-source=quota-symbolic.svg \
  --extra-source=codex-logo.svg --extra-source=claude-logo.svg .
```

The Codex mark comes from [Lobe Icons](https://github.com/lobehub/lobe-icons), with its monochrome fill set to white for the dark card. The Claude mark comes from the installed Anthropic Claude Code VS Code extension. They identify providers in account cards and the top bar. The card layout takes cues from [compact activity cards](https://dribbble.com/shots/26677688-UI-cards) and an [AI usage widget](https://dribbble.com/shots/27698368-Design-Case-Study-6-AI-Usage-Widget-Limits-That-Live-on-Your) on Dribbble.
