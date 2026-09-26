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
        this._indicator = new PanelMenu.Button(0.0, 'Quota Tray');
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        const icon = Gio.File.new_for_path(GLib.build_filenamev([this.path, 'quota-symbolic.svg']));
        box.add_child(new St.Icon({gicon: new Gio.FileIcon({file: icon}), style_class: 'system-status-icon'}));
        this._label = new St.Label({text: 'AI …', y_align: Clutter.ActorAlign.CENTER});
        box.add_child(this._label);
        this._indicator.add_child(box);
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
        this._label = null;
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
        this._label.text = 'AI !';
        this._indicator.menu.removeAll();
        const item = new PopupMenu.PopupMenuItem(message, {reactive: false});
        this._indicator.menu.addMenuItem(item);
        this._addFooter();
    }

    _render(result) {
        this._indicator.menu.removeAll();
        const accounts = result.accounts ?? [];
        if (accounts.length === 0) {
            this._label.text = 'AI +';
            this._indicator.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                'Add a Codex or Claude account with quota.py add', {reactive: false}));
            this._addFooter();
            return;
        }

        const summaries = [];
        for (const account of accounts) {
            const name = `${account.provider === 'codex' ? 'C' : 'A'} ${account.label}`;
            const windows = account.windows ?? [];
            const remaining = windows.length ? Math.min(...windows.map(w => Math.max(0, 100 - w.used))) : null;
            summaries.push(`${name} ${remaining === null ? '!' : `${Math.round(remaining)}%`}`);
            const section = new PopupMenu.PopupMenuSection();
            section.addMenuItem(new PopupMenu.PopupMenuItem(name, {reactive: false}));
            if (account.error) {
                section.addMenuItem(new PopupMenu.PopupMenuItem(account.error, {reactive: false}));
            } else if (windows.length === 0) {
                section.addMenuItem(new PopupMenu.PopupMenuItem('No quota windows returned', {reactive: false}));
            } else {
                for (const window of windows) {
                    const reset = window.reset ? ` · resets ${window.reset}` : '';
                    section.addMenuItem(new PopupMenu.PopupMenuItem(
                        `${window.name}: ${Math.round(100 - window.used)}% left${reset}`,
                        {reactive: false}));
                }
            }
            this._indicator.menu.addMenuItem(section);
            this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        }
        this._label.text = summaries.join('  ');
        this._addFooter();
    }

    _addFooter() {
        const refresh = new PopupMenu.PopupMenuItem('Refresh now');
        refresh.connect('activate', () => this._refresh());
        this._indicator.menu.addMenuItem(refresh);
    }
}
