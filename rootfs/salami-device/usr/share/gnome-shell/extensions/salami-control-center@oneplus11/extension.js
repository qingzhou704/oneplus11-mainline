// SPDX-License-Identifier: GPL-2.0-only
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const SALAMI_CTL = '/usr/bin/salami-ctl';
const PERF_MODES = [
    {id: 'eco', label: '节能静音 (≤1.84 GHz)', short: '节能静音'},
    {id: 'balanced', label: '日常均衡 (默认动态)', short: '日常均衡'},
    {id: 'performance', label: '满血性能 (3.19 GHz 睿频)', short: '满血性能'},
];

function runCtlAsync(args, onDone = null) {
    try {
        const proc = Gio.Subprocess.new(
            [SALAMI_CTL, ...args],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        );
        proc.communicate_utf8_async(null, null, (p, res) => {
            try {
                const [, stdout, stderr] = p.communicate_utf8_finish(res);
                const ok = p.get_successful();
                onDone?.(ok, (stdout ?? '').trim(), (stderr ?? '').trim());
            } catch (e) {
                onDone?.(false, '', String(e));
            }
        });
    } catch (e) {
        onDone?.(false, '', String(e));
    }
}

const SalamiTopBarButton = GObject.registerClass(
class SalamiTopBarButton extends PanelMenu.Button {
    _init() {
        super._init(1.0, 'OnePlus 11 Control Center', false);

        this._statusData = null;
        this._netData = null;
        this._timedChargeTag = null;
        this._hideFlyoutTimerId = 0;

        const panelBox = new St.BoxLayout({style_class: 'panel-status-menu-box salami-panel-box'});
        this._panelIcon = new St.Icon({
            icon_name: 'phone-symbolic',
            style_class: 'system-status-icon',
            icon_size: 16,
        });
        this._panelLabel = new St.Label({
            text: '...',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'salami-panel-label',
        });
        panelBox.add_child(this._panelIcon);
        panelBox.add_child(this._panelLabel);
        this.add_child(panelBox);

        this._ifaceSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._colorSchemeId = this._ifaceSettings.connect('changed::color-scheme', () => {
            this._applyThemeClass();
        });

        this._setupDualCardLayout();
        this.refreshAll(true);
    }

    _isDarkTheme() {
        const scheme = this._ifaceSettings?.get_string('color-scheme') ?? 'default';
        return scheme === 'prefer-dark';
    }

    _cardClass(extra) {
        const base = this._isDarkTheme() ? 'salami-card-dark' : 'salami-card-light';
        return `${base} ${extra}`;
    }

    _applyThemeClass() {
        if (this._mainCard)
            this._mainCard.style_class = this._cardClass('salami-main-card');
        if (this._flyoutCard)
            this._flyoutCard.style_class = this._cardClass('salami-flyout-card');
    }

    _setupDualCardLayout() {
        this.menu.box.style_class = 'salami-dual-root';
        if (this.menu.actor._border)
            this.menu.actor._border.hide();

        this._hbox = new St.BoxLayout({
            vertical: false,
            style_class: 'salami-dual-hbox',
        });
        this.menu.box.add_child(this._hbox);

        // Transparent left slot holds the hover flyout card so the main card never shifts.
        this._flyoutSlot = new St.Widget({
            style_class: 'salami-flyout-slot',
            layout_manager: new Clutter.BinLayout(),
            reactive: true,
            y_expand: true,
        });
        this._flyoutSlot.connect('button-press-event', (_actor, event) => {
            const target = global.stage.get_event_actor(event);
            if (!this._flyoutCard?.visible || !this._flyoutCard.contains(target)) {
                this.menu.close();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        this._flyoutCard = new St.BoxLayout({
            vertical: true,
            style_class: this._cardClass('salami-flyout-card'),
            reactive: true,
            track_hover: true,
            x_align: Clutter.ActorAlign.END,
            y_align: Clutter.ActorAlign.START,
            visible: false,
        });
        this._flyoutCard.connect('notify::hover', () => {
            if (this._flyoutCard.hover)
                this._cancelHideFlyout();
            else
                this._scheduleHideFlyout();
        });
        this._flyoutSlot.add_child(this._flyoutCard);

        this._mainCard = new St.BoxLayout({
            vertical: true,
            style_class: this._cardClass('salami-main-card'),
            reactive: true,
            y_align: Clutter.ActorAlign.START,
        });

        this._hbox.add_child(this._flyoutSlot);
        this._hbox.add_child(this._mainCard);

        const summaryBtn = new St.BoxLayout({
            vertical: true,
            reactive: true,
            track_hover: true,
            style_class: 'salami-summary-box',
        });
        summaryBtn.connect('notify::hover', () => {
            if (summaryBtn.hover)
                this._hideFlyoutImmediate();
        });
        summaryBtn.connect('button-press-event', () => {
            this.refreshAll(true);
            return Clutter.EVENT_STOP;
        });

        const titleRow = new St.BoxLayout({style_class: 'salami-summary-title-row'});
        titleRow.add_child(new St.Label({
            text: '一加 11 控制台',
            x_expand: true,
            style_class: 'salami-summary-title',
        }));
        titleRow.add_child(new St.Label({
            text: '刷新',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'salami-summary-hint',
        }));
        this._sumLine1 = new St.Label({text: '电池读取中...', style_class: 'salami-summary-line'});
        this._sumLine2 = new St.Label({text: '状态读取中...', style_class: 'salami-summary-line'});
        summaryBtn.add_child(titleRow);
        summaryBtn.add_child(this._sumLine1);
        summaryBtn.add_child(this._sumLine2);
        this._mainCard.add_child(summaryBtn);
        this._mainCard.add_child(new St.Widget({style_class: 'salami-sep'}));

        this._catRows = new Map();
        const categories = [
            ['perf', '性能模式'],
            ['power', '充电与快充'],
            ['display', '屏幕与刷新率'],
            ['touch', '触控与手电筒'],
            ['rdp', '远程桌面画质'],
            ['network', '网络与服务'],
        ];
        for (const [key, title] of categories) {
            const row = new St.BoxLayout({
                reactive: true,
                track_hover: true,
                style_class: 'salami-cat-row',
            });
            const lbl = new St.Label({
                text: title,
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
                style_class: 'salami-cat-label',
            });
            const valLbl = new St.Label({
                text: '',
                y_align: Clutter.ActorAlign.CENTER,
                style_class: 'salami-cat-value',
            });
            const arrow = new St.Label({
                text: '›',
                y_align: Clutter.ActorAlign.CENTER,
                style_class: 'salami-cat-arrow',
            });
            row.add_child(lbl);
            row.add_child(valLbl);
            row.add_child(arrow);

            row.connect('notify::hover', () => {
                if (row.hover) {
                    this._cancelHideFlyout();
                    this._openCategoryFlyout(key, row);
                } else {
                    this._scheduleHideFlyout();
                }
            });
            row.connect('button-press-event', () => {
                this._cancelHideFlyout();
                this._openCategoryFlyout(key, row);
                return Clutter.EVENT_STOP;
            });

            this._catRows.set(key, {row, valLbl});
            this._mainCard.add_child(row);
        }

        this.menu.connect('open-state-changed', (_menu, isOpen) => {
            if (isOpen)
                this.refreshAll(false);
            else
                this._hideFlyoutImmediate();
        });
    }

    _cancelHideFlyout() {
        if (this._hideFlyoutTimerId) {
            GLib.source_remove(this._hideFlyoutTimerId);
            this._hideFlyoutTimerId = 0;
        }
    }

    _scheduleHideFlyout() {
        this._cancelHideFlyout();
        this._hideFlyoutTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 180, () => {
            this._hideFlyoutTimerId = 0;
            const anyCatHovered = Array.from(this._catRows.values()).some(c => c.row.hover);
            if (!anyCatHovered && !this._flyoutCard?.hover)
                this._hideFlyoutImmediate();
            return GLib.SOURCE_REMOVE;
        });
    }

    _hideFlyoutImmediate() {
        this._cancelHideFlyout();
        for (const {row} of this._catRows.values())
            row.style_class = 'salami-cat-row';
        if (this._flyoutCard) {
            this._flyoutCard.hide();
            this._flyoutCard.destroy_all_children();
        }
    }

    _addSubItem(label, mark, onActivate, sensitive = true) {
        const row = new St.BoxLayout({
            reactive: sensitive,
            track_hover: sensitive,
            style_class: 'salami-sub-row',
            opacity: sensitive ? 255 : 120,
        });
        const markLbl = new St.Label({
            text: mark,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'salami-sub-mark',
        });
        const textLbl = new St.Label({
            text: label,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'salami-sub-label',
        });
        row.add_child(markLbl);
        row.add_child(textLbl);
        if (sensitive && onActivate) {
            row.connect('button-press-event', () => {
                onActivate();
                return Clutter.EVENT_STOP;
            });
        }
        this._flyoutCard.add_child(row);
    }

    _addSubSep() {
        this._flyoutCard.add_child(new St.Widget({style_class: 'salami-sep'}));
    }

    _addSubNote(text) {
        this._flyoutCard.add_child(new St.Label({
            text,
            style_class: 'salami-sub-note',
        }));
    }

    _openCategoryFlyout(key, rowActor) {
        for (const [k, {row}] of this._catRows.entries())
            row.style_class = k === key ? 'salami-cat-row salami-cat-row-active' : 'salami-cat-row';

        this._flyoutCard.destroy_all_children();
        const st = this._statusData;
        const net = this._netData;

        if (key === 'perf') {
            const cur = st?.perf?.mode ?? 'balanced';
            for (const entry of PERF_MODES) {
                this._addSubItem(entry.label, cur === entry.id ? '•' : '', () => {
                    this.menu.close();
                    runCtlAsync(['perf', entry.id], () => this.refreshAll(false));
                });
            }
        } else if (key === 'power') {
            const endThr = st?.battery?.end_threshold_pct ?? 80;
            const curTag = endThr <= 80 ? '80' : (this._timedChargeTag ?? '100_keep');
            const presets = [
                ['80', '日常 80% 护航限充', ['charge', '80']],
                ['100_6h', '临时充满 100% (6 小时恢复)', ['charge', '100', '--hours', '6']],
                ['100_12h', '临时充满 100% (12 小时恢复)', ['charge', '100', '--hours', '12']],
                ['100_keep', '保持 100% 满充上限', ['charge', '100']],
            ];
            for (const [tag, text, cmd] of presets) {
                this._addSubItem(text, curTag === tag ? '•' : '', () => {
                    this._timedChargeTag = tag === '80' ? null : tag;
                    this.menu.close();
                    runCtlAsync(cmd, () => this.refreshAll(false));
                });
            }
            this._addSubSep();
            const voocOn = Boolean(st?.battery?.vooc_enabled ?? true);
            this._addSubItem('允许 SUPERVOOC 50W 闪充', voocOn ? '✓' : '', () => {
                this.menu.close();
                runCtlAsync(['vooc', voocOn ? 'off' : 'on'], () => this.refreshAll(false));
            });
        } else if (key === 'display') {
            const scrOn = String(st?.display?.dpms ?? 'On').toLowerCase() === 'on';
            const hbmSup = Boolean(st?.display?.hbm_supported);
            const hbmOn = Boolean(st?.display?.hbm_enabled);
            const curHz = Number(st?.display?.refresh_hz ?? st?.display?.configured_refresh_hz ?? 120);
            const curPct = Number(st?.display?.brightness_pct ?? 50);

            this._addSubItem('手机物理屏幕亮起', scrOn ? '✓' : '', () => {
                this.menu.close();
                runCtlAsync(['screen', scrOn ? 'off' : 'on'], () => this.refreshAll(false));
            });
            this._addSubItem(
                hbmSup ? '阳光屏户外超亮激发 (HBM)' : '阳光屏超亮激发 (不可用)',
                hbmOn ? '✓' : '',
                () => {
                    this.menu.close();
                    runCtlAsync(['hbm', hbmOn ? 'off' : 'on'], () => this.refreshAll(false));
                },
                hbmSup
            );
            this._addSubSep();
            for (const hz of [120, 90, 60]) {
                this._addSubItem(`屏幕刷新率 ${hz} Hz`, curHz === hz ? '•' : '', () => {
                    this.menu.close();
                    runCtlAsync(['refresh', String(hz)], () => this.refreshAll(false));
                });
            }
            this._addSubSep();
            const brLevels = [15, 35, 60, 85, 100];
            const nearBr = brLevels.reduce((a, b) => (Math.abs(b - curPct) < Math.abs(a - curPct) ? b : a), 35);
            for (const pct of brLevels) {
                this._addSubItem(`屏幕亮度 ${pct}%`, nearBr === pct ? '•' : '', () => {
                    this.menu.close();
                    runCtlAsync(['brightness', `${pct}%`], () => this.refreshAll(false));
                });
            }
        } else if (key === 'touch') {
            const offPol = st?.touch?.off_policy ?? 'gesture';
            const gloveSup = Boolean(st?.touch?.glove_supported);
            const gloveOn = Boolean(st?.touch?.glove_enabled);
            const torchVal = Number(st?.torch?.brightness ?? 0);

            for (const [pol, label] of [
                ['gesture', '息屏双击亮屏唤醒'],
                ['sleep', '息屏彻底休眠断触'],
                ['active', '息屏单点触控唤醒'],
            ]) {
                this._addSubItem(label, offPol === pol ? '•' : '', () => {
                    this.menu.close();
                    runCtlAsync(['touch', 'off-policy', pol], () => this.refreshAll(false));
                });
            }
            this._addSubSep();
            this._addSubItem('手套 / 湿手高灵敏触控', gloveOn ? '✓' : '', () => {
                this.menu.close();
                runCtlAsync(['touch', 'glove', gloveOn ? 'off' : 'on'], () => this.refreshAll(false));
            }, gloveSup);
            this._addSubSep();
            const torchPresets = [
                [0, '关闭手电筒'],
                [24, '手电筒 · 弱光'],
                [64, '手电筒 · 标准'],
                [180, '手电筒 · 强光'],
            ];
            const activeTorch = torchVal <= 0
                ? 0
                : [24, 64, 180].reduce((a, b) => (Math.abs(b - torchVal) < Math.abs(a - torchVal) ? b : a), 64);
            for (const [lv, label] of torchPresets) {
                this._addSubItem(label, activeTorch === lv ? '•' : '', () => {
                    this.menu.close();
                    runCtlAsync(['torch', lv === 0 ? 'off' : String(lv)], () => this.refreshAll(false));
                });
            }
            this._addSubSep();
            this._addSubItem('震动手机一下 (寻机)', '', () => {
                this.menu.close();
                runCtlAsync(['vibrate', '80']);
            });
        } else if (key === 'rdp') {
            const curQp = Number(st?.rdp_vaapi_qp ?? 22);
            const presets = [
                [18, 'hq', '高画质锐利 (QP 18)'],
                [22, 'balanced', '日常均衡 (QP 22)'],
                [27, 'fast', '顺滑低码率 (QP 27)'],
            ];
            const nearQp = presets.reduce((a, b) => (Math.abs(b[0] - curQp) < Math.abs(a[0] - curQp) ? b : a))[0];
            for (const [qp, keyName, label] of presets) {
                this._addSubItem(label, nearQp === qp ? '•' : '', () => {
                    this.menu.close();
                    runCtlAsync(['rdp', keyName], (_ok, out) => {
                        Main.notify('一加 11 控制台', out || `远程桌面画质已设为 ${label}`);
                        this.refreshAll(false);
                    });
                });
            }
        } else if (key === 'network') {
            const mdm = net?.modem;
            if (mdm?.present) {
                const carrier = mdm.operator_name || mdm.operator_code || '蜂窝';
                const sig = mdm.signal_pct !== null && mdm.signal_pct !== undefined ? ` · ${mdm.signal_pct}%` : '';
                this._addSubNote(`5G 基带: ${carrier} · ${mdm.state}${sig}`);
            }
            this._addSubItem('重连自愈 5G 蜂窝基带', '', () => {
                this.menu.close();
                runCtlAsync(['modem', 'recover'], (_ok, out, err) => {
                    Main.notify('一加 11 控制台', out || err || '5G 基带重连已执行');
                    this.refreshAll(true);
                });
            });
            this._addSubItem('查看系统安全加固状态', '', () => {
                this.menu.close();
                runCtlAsync(['security'], (_ok, out, err) => {
                    Main.notify('安全加固状态', out || err);
                });
            });
            this._addSubItem('执行 UFS 闪存 TRIM 优化', '', () => {
                this.menu.close();
                runCtlAsync(['fstrim'], (_ok, out, err) => {
                    Main.notify('UFS 闪存优化', out || err || '已完成');
                });
            });
            const actions = net?.managed_actions ?? [];
            if (actions.length > 0) {
                this._addSubSep();
                for (const item of actions) {
                    const verbLabel = item.verb === 'reload' ? '重载' : '重启';
                    const svcKey = item.unit.replace(/\.service$/, '');
                    const ok = net?.services?.[svcKey] === 'active';
                    this._addSubItem(`${verbLabel} ${item.label}`, ok ? '•' : '', () => {
                        this.menu.close();
                        runCtlAsync(['service', item.unit], (_sOk, out, err) => {
                            Main.notify('服务运维', out || err || `已${verbLabel} ${item.label}`);
                            this.refreshAll(true);
                        });
                    });
                }
            }
        }

        this._flyoutCard.translation_y = 0;
        this._flyoutCard.show();

        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            if (!this._flyoutCard?.visible || !this._mainCard)
                return GLib.SOURCE_REMOVE;
            const [, mainY] = this._mainCard.get_transformed_position();
            const [, rowY] = rowActor.get_transformed_position();
            const [, mainH] = this._mainCard.get_transformed_size();
            const [, flyH] = this._flyoutCard.get_preferred_height(-1);
            const desiredOffset = Math.max(0, rowY - mainY - 6);
            const maxOffset = Math.max(0, mainH - flyH);
            this._flyoutCard.translation_y = Math.round(Math.min(desiredOffset, maxOffset));
            return GLib.SOURCE_REMOVE;
        });
    }

    refreshAll(includeNet = false) {
        runCtlAsync(['status', '--json'], (ok, stdout) => {
            if (!ok || !stdout)
                return;
            try {
                this._statusData = JSON.parse(stdout);
                this._renderSummary();
            } catch {
                // ignore malformed output
            }
        });
        if (includeNet || !this._netData) {
            runCtlAsync(['net', '--json'], (ok, stdout) => {
                if (!ok || !stdout)
                    return;
                try {
                    this._netData = JSON.parse(stdout);
                    this._renderSummary();
                } catch {
                    // ignore malformed output
                }
            });
        }
    }

    _renderSummary() {
        const st = this._statusData;
        if (!st || !this._panelLabel)
            return;

        const bat = st.battery ?? {};
        const therm = st.thermals_c ?? {};
        const perfMode = st.perf?.mode ?? 'balanced';
        const cap = bat.capacity_pct;
        const watts = Number(bat.power_w ?? 0);
        const cpuT = therm.cpu_max;

        let pText = cap !== null && cap !== undefined ? `${cap}%` : 'OP11';
        if (watts >= 0.8 && bat.status === 'Charging')
            pText = `${Math.round(watts)}W`;
        const tText = cpuT !== null && cpuT !== undefined ? ` · ${Math.round(cpuT)}°C` : '';
        this._panelLabel.text = `${pText}${tText}`;

        if (watts >= 5.0 && bat.status === 'Charging')
            this._panelIcon.icon_name = 'battery-good-charging-symbolic';
        else if (perfMode === 'performance')
            this._panelIcon.icon_name = 'power-profile-performance-symbolic';
        else if (perfMode === 'eco')
            this._panelIcon.icon_name = 'power-profile-power-saver-symbolic';
        else
            this._panelIcon.icon_name = 'phone-symbolic';

        const wDesc = watts >= 0.1 ? `${watts.toFixed(1)} W` : '稳压 0 W';
        this._sumLine1.text = `电池 ${cap ?? '?'}% (限 ${bat.end_threshold_pct ?? 80}%) · ${wDesc} · ${bat.temp_c ?? '?'} °C`;

        const mem = st.memory ?? {};
        const svcs = this._netData?.services ?? {};
        const svcKeys = Object.keys(svcs);
        const svcOk = svcKeys.filter(k => svcs[k] === 'active').length;
        const svcPart = svcKeys.length > 0 ? ` · 服务 ${svcOk}/${svcKeys.length}` : '';
        this._sumLine2.text = `CPU ${cpuT ?? '?'} °C · RAM ${mem.ram_used_gib ?? '?'}/${mem.ram_total_gib ?? '?'}G${svcPart}`;

        const perfShort = PERF_MODES.find(m => m.id === perfMode)?.short ?? '日常均衡';
        this._catRows.get('perf').valLbl.text = perfShort;

        const endThr = bat.end_threshold_pct ?? 80;
        const voocStr = bat.vooc_enabled ? '闪充' : '慢充';
        this._catRows.get('power').valLbl.text = `限 ${endThr}% · ${voocStr}`;

        const scrOn = String(st.display?.dpms ?? 'On').toLowerCase() === 'on';
        const hz = st.display?.refresh_hz ?? st.display?.configured_refresh_hz ?? 120;
        this._catRows.get('display').valLbl.text = `${scrOn ? '亮屏' : '息屏'} · ${hz}Hz`;

        const polMap = {gesture: '双击亮屏', sleep: '息屏断触', active: '单点唤醒'};
        const polTxt = polMap[st.touch?.off_policy ?? 'gesture'] ?? '双击亮屏';
        const torchOn = Number(st.torch?.brightness ?? 0) > 0;
        this._catRows.get('touch').valLbl.text = torchOn ? '手电已开' : polTxt;

        const qp = Number(st.rdp_vaapi_qp ?? 22);
        const qpLabel = qp <= 19 ? '高画质' : (qp >= 25 ? '低码率' : '均衡');
        this._catRows.get('rdp').valLbl.text = `${qpLabel} QP${qp}`;

        this._catRows.get('network').valLbl.text = svcKeys.length > 0
            ? `${svcOk}/${svcKeys.length} 正常`
            : (st.network?.tcp_congestion_control ?? 'bbr');
    }

    destroy() {
        this._cancelHideFlyout();
        if (this._colorSchemeId && this._ifaceSettings) {
            this._ifaceSettings.disconnect(this._colorSchemeId);
            this._colorSchemeId = 0;
        }
        this._ifaceSettings = null;
        super.destroy();
    }
});

export default class SalamiControlCenterExtension extends Extension {
    enable() {
        try {
            Gio.Subprocess.new(
                ['/usr/bin/systemctl', '--user', 'stop', 'salami-tray.service'],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
            );
        } catch {
            // ignore if systemd user unit is absent
        }
        if (!this._topBarBtn && Main.panel?.addToStatusArea) {
            this._topBarBtn = new SalamiTopBarButton();
            Main.panel.addToStatusArea('salami-control-center', this._topBarBtn, 1, 'right');
        }
        let netTick = 0;
        this._timerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 15, () => {
            netTick = (netTick + 1) % 4;
            this._topBarBtn?.refreshAll(netTick === 0);
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        if (this._timerId) {
            GLib.source_remove(this._timerId);
            this._timerId = 0;
        }
        if (this._topBarBtn) {
            this._topBarBtn.destroy();
            this._topBarBtn = null;
        }
    }
}
