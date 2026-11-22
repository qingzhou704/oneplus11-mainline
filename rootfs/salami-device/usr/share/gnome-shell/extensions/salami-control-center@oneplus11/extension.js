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

function formatDurationShort(seconds) {
    if (!seconds || seconds <= 0)
        return '';
    if (seconds < 60)
        return '<1m';
    const mins = Math.floor((seconds + 30) / 60);
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    if (hours > 0)
        return remMins ? `${hours}h${String(remMins).padStart(2, '0')}m` : `${hours}h`;
    return `${remMins}m`;
}

function formatPowerDesc(watts, status) {
    const absW = Math.abs(Number(watts ?? 0));
    if (absW < 0.1)
        return '稳压 0 W';
    if (status === 'Discharging')
        return `放电 ${absW.toFixed(1)} W`;
    if (status === 'Charging')
        return `充电 ${absW.toFixed(1)} W`;
    return `${absW.toFixed(1)} W`;
}

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
        this._positionFlyoutIdleId = 0;
        this._activeFlyoutKey = null;
        this._activeRowActor = null;

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
                if (this._activeFlyoutKey === key && this._flyoutCard?.visible && !row.hover)
                    this._hideFlyoutImmediate();
                else
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

    _cancelPositionFlyout() {
        if (this._positionFlyoutIdleId) {
            GLib.source_remove(this._positionFlyoutIdleId);
            this._positionFlyoutIdleId = 0;
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
        this._cancelPositionFlyout();
        this._activeFlyoutKey = null;
        this._activeRowActor = null;
        for (const {row} of this._catRows.values())
            row.style_class = 'salami-cat-row';
        if (this._flyoutCard) {
            this._flyoutCard.hide();
            this._flyoutCard.destroy_all_children();
        }
    }

    _runAction(args, errTitle, {refreshNet = false, okTitle = null, okFallback = ''} = {}) {
        this.menu.close();
        runCtlAsync(args, (ok, out, err) => {
            if (!ok)
                Main.notify(errTitle, err || out || '执行失败');
            else if (okTitle)
                Main.notify(okTitle, out || okFallback);
            this.refreshAll(refreshNet);
        });
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

    _addServiceRow(item, active) {
        const container = new St.BoxLayout({
            vertical: false,
            style_class: 'salami-svc-row',
        });

        const verbLabel = active ? (item.verb === 'reload' ? '重载' : '重启') : '启动';
        const mainAct = active ? item.verb : 'start';
        const mainRow = new St.BoxLayout({
            reactive: true,
            track_hover: true,
            x_expand: true,
            style_class: 'salami-sub-row salami-svc-main',
        });
        mainRow.add_child(new St.Label({
            text: active ? '•' : '',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'salami-sub-mark',
        }));
        mainRow.add_child(new St.Label({
            text: `${verbLabel} ${item.label}`,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'salami-sub-label',
        }));
        mainRow.connect('button-press-event', () => {
            this._runAction(['service', item.unit, mainAct], `${verbLabel} ${item.label} 失败`, {
                refreshNet: true,
                okTitle: '服务运维',
                okFallback: `已${verbLabel} ${item.label}`,
            });
            return Clutter.EVENT_STOP;
        });

        const sideAct = active ? 'stop' : 'start';
        const sideVerb = active ? '停止' : '启动';
        const sideBtn = new St.Button({
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
            accessible_name: `${sideVerb} ${item.label}`,
            style_class: active
                ? 'salami-svc-icon-btn salami-svc-stop-btn'
                : 'salami-svc-icon-btn salami-svc-start-btn',
            child: new St.Icon({
                icon_name: active ? 'media-playback-stop-symbolic' : 'media-playback-start-symbolic',
                icon_size: 14,
            }),
        });
        sideBtn.connect('clicked', () => {
            this._runAction(['service', item.unit, sideAct], `${sideVerb} ${item.label} 失败`, {
                refreshNet: true,
                okTitle: '服务运维',
                okFallback: `已${sideVerb} ${item.label}`,
            });
        });

        container.add_child(mainRow);
        container.add_child(sideBtn);
        this._flyoutCard.add_child(container);
    }

    _openCategoryFlyout(key, rowActor) {
        this._activeFlyoutKey = key;
        this._activeRowActor = rowActor;
        for (const [k, {row}] of this._catRows.entries())
            row.style_class = k === key ? 'salami-cat-row salami-cat-row-active' : 'salami-cat-row';

        this._flyoutCard.destroy_all_children();
        const st = this._statusData;
        const net = this._netData;

        if (key === 'perf') {
            const cur = st?.perf?.mode ?? 'balanced';
            for (const entry of PERF_MODES) {
                this._addSubItem(entry.label, cur === entry.id ? '•' : '', () => {
                    this._runAction(['perf', entry.id], '切换性能模式失败');
                });
            }
        } else if (key === 'power') {
            const endThr = st?.battery?.end_threshold_pct ?? 80;
            const remS = Number(st?.battery?.restore_timer_remaining_s ?? 0);
            if (remS > 0)
                this._addSubNote(`定时恢复倒计时: 剩余 ${formatDurationShort(remS)}`);
            let curTag = '100_keep';
            if (endThr <= 80)
                curTag = '80';
            else if (remS > 0)
                curTag = this._timedChargeTag ?? (remS > 6 * 3600 ? '100_12h' : '100_6h');
            else
                curTag = '100_keep';
            const presets = [
                ['80', '日常 80% 护航限充', ['charge', '80']],
                ['100_6h', '临时充满 100% (6 小时恢复)', ['charge', '100', '--hours', '6']],
                ['100_12h', '临时充满 100% (12 小时恢复)', ['charge', '100', '--hours', '12']],
                ['100_keep', '保持 100% 满充上限', ['charge', '100']],
            ];
            for (const [tag, text, cmd] of presets) {
                this._addSubItem(text, curTag === tag ? '•' : '', () => {
                    this._timedChargeTag = tag === '80' || tag === '100_keep' ? null : tag;
                    this._runAction(cmd, '更新充电上限失败');
                });
            }
            this._addSubSep();
            const voocOn = Boolean(st?.battery?.vooc_enabled ?? true);
            const coolLv = Number(st?.battery?.vooc_cool_down ?? 0);
            const voocMode = !voocOn ? 'slow' : (coolLv > 0 ? 'cool' : 'fast');
            for (const [tag, label, cmd] of [
                ['fast', 'SUPERVOOC 50W 全速闪充', ['vooc', 'on', '--cool', '0']],
                ['cool', 'SUPERVOOC 温和限流快充', ['vooc', 'on', '--cool', '8']],
                ['slow', '10W 低温慢充护航', ['vooc', 'off']],
            ]) {
                this._addSubItem(label, voocMode === tag ? '•' : '', () => {
                    this._runAction(cmd, '切换快充模式失败');
                });
            }
        } else if (key === 'display') {
            const scrOn = String(st?.display?.dpms ?? 'On').toLowerCase() === 'on';
            const hbmSup = Boolean(st?.display?.hbm_supported);
            const hbmOn = Boolean(st?.display?.hbm_enabled);
            const curHz = Number(st?.display?.refresh_hz ?? st?.display?.configured_refresh_hz ?? 120);
            const curPct = Number(st?.display?.brightness_pct ?? 50);

            this._addSubItem('手机物理屏幕亮起', scrOn ? '✓' : '', () => {
                this._runAction(['screen', scrOn ? 'off' : 'on'], '控制物理屏幕失败');
            });
            this._addSubItem(
                hbmSup ? '阳光屏户外超亮激发 (HBM)' : '阳光屏超亮激发 (不可用)',
                hbmOn ? '✓' : '',
                () => {
                    this._runAction(['hbm', hbmOn ? 'off' : 'on'], '切换阳光屏 HBM 失败');
                },
                hbmSup
            );
            this._addSubSep();
            for (const hz of [120, 90, 60]) {
                this._addSubItem(`屏幕刷新率 ${hz} Hz`, curHz === hz ? '•' : '', () => {
                    this._runAction(['refresh', String(hz)], '切换刷新率失败');
                });
            }
            this._addSubSep();
            const brLevels = [15, 35, 60, 85, 100];
            const nearBr = brLevels.reduce((a, b) => (Math.abs(b - curPct) < Math.abs(a - curPct) ? b : a), 35);
            for (const pct of brLevels) {
                this._addSubItem(`屏幕亮度 ${pct}%`, nearBr === pct ? '•' : '', () => {
                    this._runAction(['brightness', `${pct}%`], '调节屏幕亮度失败');
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
                    this._runAction(['touch', 'off-policy', pol], '更新息屏触控策略失败');
                });
            }
            this._addSubSep();
            this._addSubItem('手套 / 湿手高灵敏触控', gloveOn ? '✓' : '', () => {
                this._runAction(['touch', 'glove', gloveOn ? 'off' : 'on'], '切换手套触控失败');
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
                    this._runAction(['torch', lv === 0 ? 'off' : String(lv)], '控制手电筒失败');
                });
            }
            this._addSubSep();
            this._addSubItem('震动手机一下 (寻机)', '', () => {
                this._runAction(['vibrate', '80'], '触发手机震动失败');
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
                    this._runAction(['rdp', keyName], '设置远程桌面画质失败', {
                        okTitle: '一加 11 控制台',
                        okFallback: `远程桌面画质已设为 ${label}`,
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
            this._addSubItem('运行一键系统体检 (Doctor)', '', () => {
                this.menu.close();
                runCtlAsync(['doctor'], (_ok, out, err) => {
                    Main.notify('一加 11 系统体检', out || err || '体检已完成');
                });
            });
            this._addSubItem('重连自愈 5G 蜂窝基带', '', () => {
                this._runAction(['modem', 'recover'], '5G 基带重连失败', {
                    refreshNet: true,
                    okTitle: '一加 11 控制台',
                    okFallback: '5G 基带重连已执行',
                });
            });
            this._addSubItem('查看系统安全加固状态', '', () => {
                this._runAction(['security'], '读取安全加固状态失败', {
                    okTitle: '安全加固状态',
                });
            });
            this._addSubItem('执行 UFS 闪存 TRIM 优化', '', () => {
                this._runAction(['fstrim'], 'UFS 闪存 TRIM 失败', {
                    okTitle: 'UFS 闪存优化',
                    okFallback: '已完成',
                });
            });
            const actions = net?.managed_actions ?? [];
            if (actions.length > 0) {
                this._addSubSep();
                for (const item of actions) {
                    const svcKey = item.unit.replace(/\.service$/, '');
                    const active = net?.services?.[svcKey] === 'active';
                    this._addServiceRow(item, active);
                }
            }
        }

        this._flyoutCard.translation_y = 0;
        this._flyoutCard.show();

        this._cancelPositionFlyout();
        this._positionFlyoutIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._positionFlyoutIdleId = 0;
            if (!this._flyoutCard?.visible || !this._mainCard || !rowActor)
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

        const wDesc = formatPowerDesc(watts, bat.status);
        const remS = Number(bat.restore_timer_remaining_s ?? 0);
        const limDesc = remS > 0 ? `限 ${bat.end_threshold_pct ?? 100}%·剩${formatDurationShort(remS)}` : `限 ${bat.end_threshold_pct ?? 80}%`;
        this._sumLine1.text = `电池 ${cap ?? '?'}% (${limDesc}) · ${wDesc} · ${bat.temp_c ?? '?'} °C`;

        const mem = st.memory ?? {};
        const svcs = this._netData?.services ?? {};
        const svcKeys = Object.keys(svcs);
        const svcOk = svcKeys.filter(k => svcs[k] === 'active').length;
        const svcPart = svcKeys.length > 0 ? ` · 服务 ${svcOk}/${svcKeys.length}` : '';
        this._sumLine2.text = `CPU ${cpuT ?? '?'} °C · RAM ${mem.ram_used_gib ?? '?'}/${mem.ram_total_gib ?? '?'}G${svcPart}`;

        const perfShort = PERF_MODES.find(m => m.id === perfMode)?.short ?? '日常均衡';
        this._catRows.get('perf').valLbl.text = perfShort;

        const endThr = bat.end_threshold_pct ?? 80;
        const voocStr = !bat.vooc_enabled ? '慢充' : (Number(bat.vooc_cool_down ?? 0) > 0 ? '温充' : '闪充');
        this._catRows.get('power').valLbl.text = remS > 0
            ? `剩 ${formatDurationShort(remS)} · ${voocStr}`
            : `限 ${endThr}% · ${voocStr}`;

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

        if (this._flyoutCard?.visible && this._activeFlyoutKey && this._activeRowActor)
            this._openCategoryFlyout(this._activeFlyoutKey, this._activeRowActor);
    }

    destroy() {
        this._cancelHideFlyout();
        this._cancelPositionFlyout();
        this._activeFlyoutKey = null;
        this._activeRowActor = null;
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
            const stopProc = Gio.Subprocess.new(
                ['/usr/bin/systemctl', '--user', 'stop', 'salami-tray.service'],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
            );
            stopProc.wait_async(null, null);
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
