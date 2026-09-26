import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const REFRESH_SECONDS = 300;

export default class QuotaTray extends Extension {
    enable() {
        this._generation = 0;
        this._selectedAccount = this._readSelection();
        this._indicator = new PanelMenu.Button(0.0, 'Quota Tray');
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this._panelIcon = new St.Icon({gicon: this._asset('quota-symbolic.svg'),
            style_class: 'system-status-icon', icon_size: 16});
        this._panelValue = this._text('', 'quota-panel-value');
        box.add_child(this._panelIcon);
        box.add_child(this._panelValue);
        this._indicator.add_child(box);
        this._indicator.menu.box.add_style_class_name('quota-menu');
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._indicator.menu.connect('open-state-changed', (_menu, open) => {
            if (open && GLib.get_monotonic_time() - (this._lastRefresh ?? 0) >= REFRESH_SECONDS * 1000000)
                this._refresh();
        });
        this._refresh();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        this._generation++;
        if (this._timer) {
            GLib.Source.remove(this._timer);
            this._timer = null;
        }
        this._indicator?.destroy();
        this._indicator = null;
    }

    _refresh() {
        this._lastRefresh = GLib.get_monotonic_time();
        const generation = ++this._generation;
        const helper = GLib.build_filenamev([this.path, 'quota.py']);
        const process = new Gio.Subprocess({
            argv: ['/usr/bin/python3', helper, 'poll'],
            flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
        });
        try {
            process.init(null);
        } catch (error) {
            this._showError(`Could not start quota reader: ${error.message}`);
            return;
        }
        process.communicate_utf8_async(null, null, (source, result) => {
            if (generation !== this._generation || !this._indicator)
                return;
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(result);
                if (!source.get_successful())
                    throw new Error(stderr.trim() || 'Quota reader failed');
                this._render(JSON.parse(stdout));
            } catch (error) {
                this._showError(error.message);
            }
        });
    }

    _showError(message) {
        this._panelValue.text = '—';
        this._indicator.accessible_name = 'Quota Tray: usage unavailable';
        this._indicator.menu.removeAll();
        this._addHeader('Quota Tray', 'Could not update usage');
        this._addMessage(message);
        this._addFooter();
    }

    _asset(name) {
        return new Gio.FileIcon({file: Gio.File.new_for_path(GLib.build_filenamev([this.path, name]))});
    }

    _selectionPath() {
        return GLib.build_filenamev([GLib.get_user_config_dir(), 'quota-tray', 'selection.json']);
    }

    _readSelection() {
        try {
            const [, contents] = GLib.file_get_contents(this._selectionPath());
            const selection = JSON.parse(new TextDecoder().decode(contents));
            if (typeof selection.provider === 'string' && typeof selection.label === 'string')
                return selection;
        } catch (error) {
            if (!error.matches?.(GLib.FileError, GLib.FileError.NOENT))
                logError(error, 'Could not read Quota Tray selection');
        }
        return null;
    }

    _selectAccount(account) {
        this._selectedAccount = {provider: account.provider, label: account.label};
        try {
            GLib.mkdir_with_parents(GLib.path_get_dirname(this._selectionPath()), 0o700);
            GLib.file_set_contents(this._selectionPath(), JSON.stringify(this._selectedAccount) + '\n');
        } catch (error) {
            logError(error, 'Could not save Quota Tray selection');
        }
        this._updatePanel(this._lastResult.accounts ?? []);
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            if (this._indicator)
                this._render(this._lastResult);
            return GLib.SOURCE_REMOVE;
        });
    }

    _updatePanel(accounts) {
        const selected = accounts.find(account => account.provider === this._selectedAccount?.provider &&
            account.label === this._selectedAccount?.label) ?? accounts[0];
        if (selected && (!this._selectedAccount || selected.provider !== this._selectedAccount.provider ||
            selected.label !== this._selectedAccount.label))
            this._selectedAccount = {provider: selected.provider, label: selected.label};
        this._panelIcon.gicon = this._asset(selected ? `${selected.provider}-logo.svg` : 'quota-symbolic.svg');
        const fiveHour = selected?.windows?.find(window => /(?:^|\s)5h$/i.test(window.name));
        const remaining = fiveHour ? Math.max(0, Math.min(100, 100 - fiveHour.used)) : null;
        this._panelValue.text = selected ?
            (remaining === null ? '—' : `${Math.round(remaining)}%`) : '';
        this._indicator.accessible_name = selected ?
            `${selected.provider === 'codex' ? 'Codex' : 'Claude'} ${selected.label}: ${remaining === null ?
                '5h quota unavailable' : `${this._panelValue.text} left in 5h`}` :
            'Quota Tray';
    }

    _text(value, style) {
        return new St.Label({text: value, style_class: style, y_align: Clutter.ActorAlign.CENTER});
    }

    _row(left, right, style = '') {
        const row = new St.BoxLayout({style_class: style, x_expand: true});
        left.x_expand = true;
        row.add_child(left);
        row.add_child(right);
        return row;
    }

    _addHeader(title, subtitle) {
        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        item.add_style_class_name('quota-header-item');
        const content = new St.BoxLayout({vertical: true, x_expand: true, style_class: 'quota-header'});
        content.add_child(this._text(title, 'quota-title'));
        content.add_child(this._text(subtitle, 'quota-subtitle'));
        item.add_child(content);
        this._indicator.menu.addMenuItem(item);
    }

    _addMessage(message) {
        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        item.add_style_class_name('quota-card-item');
        item.add_child(this._text(message, 'quota-message'));
        this._indicator.menu.addMenuItem(item);
    }

    _addMeter(card, window) {
        const remaining = Math.max(0, Math.min(100, 100 - window.used));
        const tone = remaining < 20 ? 'low' : remaining < 50 ? 'medium' : 'high';
        const meter = new St.BoxLayout({vertical: true, style_class: 'quota-window'});
        const name = window.name.replace(/^codex\s+/i, '');
        meter.add_child(this._row(
            this._text(name, 'quota-window-name'),
            this._text(`${Math.round(remaining)}% left`, `quota-window-value quota-value-${tone}`),
            'quota-window-heading'));
        const track = new St.BoxLayout({style_class: 'quota-track'});
        track.add_child(new St.Widget({style_class: `quota-fill quota-fill-${tone}`,
            style: `width: ${2.64 * remaining}px;`}));
        track.add_child(new St.Widget({style: `width: ${2.64 * (100 - remaining)}px;`}));
        meter.add_child(track);
        if (window.reset)
            meter.add_child(this._text(`Resets ${window.reset}`, 'quota-reset'));
        card.add_child(meter);
    }

    _addAccount(account) {
        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        item.add_style_class_name('quota-card-item');
        const selected = account.provider === this._selectedAccount?.provider &&
            account.label === this._selectedAccount?.label;
        const card = new St.BoxLayout({vertical: true, x_expand: true,
            style_class: `quota-card quota-card-${account.provider}${selected ? ' quota-card-selected' : ''}`});
        const heading = new St.BoxLayout({style_class: 'quota-account-heading'});
        const badge = new St.Bin({style_class: `quota-badge quota-badge-${account.provider}`,
            x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER});
        badge.set_child(new St.Icon({gicon: this._asset(account.provider === 'codex' ?
            'codex-logo.svg' : 'claude-logo.svg'), icon_size: 20}));
        heading.add_child(badge);
        const identity = new St.BoxLayout({vertical: true, x_expand: true, style_class: 'quota-identity'});
        const provider = account.provider === 'codex' ? 'Codex' : 'Claude';
        identity.add_child(this._text(`${provider} · ${account.label}`, 'quota-account-title'));
        if (account.email)
            identity.add_child(this._text(account.email, 'quota-email'));
        heading.add_child(identity);
        heading.add_child(this._text(selected ? 'ON BAR' : 'SHOW ON BAR',
            `quota-select-label${selected ? ' quota-select-label-active' : ''}`));
        card.add_child(heading);

        if (account.error) {
            card.add_child(this._text(account.error, 'quota-error'));
        } else if (!(account.windows ?? []).length) {
            card.add_child(this._text('No quota windows returned', 'quota-error'));
        } else {
            for (const window of account.windows)
                this._addMeter(card, window);
        }
        const button = new St.Button({style_class: 'quota-card-button', child: card, can_focus: true,
            accessible_name: `Show ${provider} ${account.label} 5h quota in top bar`});
        button.connect('clicked', () => this._selectAccount(account));
        item.add_child(button);
        this._indicator.menu.addMenuItem(item);
    }

    _render(result) {
        this._lastResult = result;
        this._indicator.menu.removeAll();
        const accounts = result.accounts ?? [];
        this._updatePanel(accounts);
        const checked = GLib.DateTime.new_now_local().format('%H:%M');
        this._addHeader('Quota Tray', `${accounts.length} ${accounts.length === 1 ? 'account' : 'accounts'} · updated ${checked}`);
        if (accounts.length === 0) {
            this._addMessage('Add an account with quota.py add');
            this._addFooter();
            return;
        }
        for (const account of accounts)
            this._addAccount(account);
        this._addFooter();
    }

    _addFooter() {
        const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        item.add_style_class_name('quota-card-item');
        const content = new St.BoxLayout({style_class: 'quota-footer-content'});
        content.add_child(new St.Icon({icon_name: 'view-refresh-symbolic', icon_size: 14}));
        content.add_child(this._text('Refresh now', 'quota-footer-label'));
        const button = new St.Button({style_class: 'quota-footer-button', child: content,
            accessible_name: 'Refresh quota now'});
        button.connect('clicked', () => this._refresh());
        item.add_child(button);
        this._indicator.menu.addMenuItem(item);
    }
}
