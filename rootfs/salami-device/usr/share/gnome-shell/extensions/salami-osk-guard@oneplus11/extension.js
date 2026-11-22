// SPDX-License-Identifier: GPL-2.0-only
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {LoginDialog} from 'resource:///org/gnome/shell/gdm/loginDialog.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {ScreenShield} from 'resource:///org/gnome/shell/ui/screenShield.js';
import {Indicator as NetworkIndicator} from 'resource:///org/gnome/shell/ui/status/network.js';

const REMOTE_AUTOLOGIN_USER_PATH = '/etc/salami/remote-autologin-user';
const BAT_DIR = '/sys/class/power_supply/qcom-battmgr-bat';
const TORCH_DIR = '/sys/class/leds/white:flash-0';
const CPUFREQ_DIR = '/sys/devices/system/cpu/cpufreq';
const GPU_DEVFREQ_DIR = '/sys/class/devfreq/3d00000.gpu';
const DEFAULT_TORCH_LEVEL = 64;
const ECO_MAX_KHZ = {
    policy0: 1555200,
    policy3: 1785600,
    policy7: 1843200,
};
const GPU_PROFILE_HZ = {
    eco: [220000000, 401000000],
    balanced: [220000000, 680000000],
    performance: [401000000, 680000000],
};
const PERF_MODES = [
    {id: 'eco', label: '节能静音 (≤1.84 GHz)', short: '节能静音', icon: 'power-profile-power-saver-symbolic'},
    {id: 'balanced', label: '日常均衡 (默认动态)', short: '日常均衡', icon: 'power-profile-balanced-symbolic'},
    {id: 'performance', label: '满血性能 (3.19 GHz 睿频)', short: '满血性能', icon: 'power-profile-performance-symbolic'},
];

function readTextFile(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        if (!ok || !bytes)
            return null;
        return new TextDecoder().decode(bytes).trim();
    } catch {
        return null;
    }
}

function readIntFile(path, fallback = null) {
    const raw = readTextFile(path);
    if (raw === null || raw === '')
        return fallback;
    const parsed = Number.parseInt(raw, 10);
    return Number.isNaN(parsed) ? fallback : parsed;
}

function writeSysfs(path, value) {
    const channel = GLib.IOChannel.new_file(path, 'w');
    try {
        channel.write_chars(`${value}\n`, -1);
    } finally {
        channel.shutdown(true);
    }
}

function detectPerfMode() {
    let allPerf = true;
    let count = 0;
    let capped = false;
    for (const name of ['policy0', 'policy3', 'policy7']) {
        const dir = `${CPUFREQ_DIR}/${name}`;
        if (!GLib.file_test(dir, GLib.FileTest.IS_DIR))
            continue;
        count++;
        const gov = readTextFile(`${dir}/scaling_governor`) ?? 'schedutil';
        const curMax = readIntFile(`${dir}/scaling_max_freq`, 0) ?? 0;
        const hwMax = readIntFile(`${dir}/cpuinfo_max_freq`, curMax) ?? curMax;
        if (gov !== 'performance')
            allPerf = false;
        if (hwMax > 0 && curMax < hwMax)
            capped = true;
    }
    if (count > 0 && allPerf && !capped)
        return 'performance';
    if (capped)
        return 'eco';
    return 'balanced';
}

function applyPerfMode(mode) {
    const boostPath = `${CPUFREQ_DIR}/boost`;
    if (GLib.file_test(boostPath, GLib.FileTest.IS_REGULAR))
        writeSysfs(boostPath, mode === 'performance' ? 1 : 0);
    const gov = mode === 'performance' ? 'performance' : 'schedutil';
    for (const name of ['policy0', 'policy3', 'policy7']) {
        const dir = `${CPUFREQ_DIR}/${name}`;
        let hwMax = readIntFile(`${dir}/cpuinfo_max_freq`);
        if (hwMax === null)
            continue;
        if (mode === 'performance') {
            const boostRaw = readTextFile(`${dir}/scaling_boost_frequencies`) ?? '';
            for (const tok of boostRaw.split(/\s+/)) {
                const bf = Number.parseInt(tok, 10);
                if (!Number.isNaN(bf) && bf > hwMax)
                    hwMax = bf;
            }
        }
        const targetMax = mode === 'eco'
            ? Math.min(hwMax, ECO_MAX_KHZ[name] ?? hwMax)
            : hwMax;
        writeSysfs(`${dir}/scaling_max_freq`, targetMax);
        writeSysfs(`${dir}/scaling_governor`, gov);
    }
    const gpuMinPath = `${GPU_DEVFREQ_DIR}/min_freq`;
    const gpuMaxPath = `${GPU_DEVFREQ_DIR}/max_freq`;
    if (GLib.file_test(gpuMinPath, GLib.FileTest.IS_REGULAR) &&
        GLib.file_test(gpuMaxPath, GLib.FileTest.IS_REGULAR)) {
        const [gMin, gMax] = GPU_PROFILE_HZ[mode] ?? GPU_PROFILE_HZ.balanced;
        const curMax = readIntFile(gpuMaxPath, 680000000) ?? 680000000;
        const curMin = readIntFile(gpuMinPath, 220000000) ?? 220000000;
        if (gMin > curMax) {
            writeSysfs(gpuMaxPath, gMax);
            writeSysfs(gpuMinPath, gMin);
        } else if (gMax < curMin) {
            writeSysfs(gpuMinPath, gMin);
            writeSysfs(gpuMaxPath, gMax);
        } else {
            writeSysfs(gpuMaxPath, gMax);
            writeSysfs(gpuMinPath, gMin);
        }
    }
}

function setChargeThresholds(limit) {
    const start = Math.max(0, limit - 5);
    const startPath = `${BAT_DIR}/charge_control_start_threshold`;
    const endPath = `${BAT_DIR}/charge_control_end_threshold`;
    const curStart = readIntFile(startPath, 0) ?? 0;
    const curEnd = readIntFile(endPath, 100) ?? 100;

    if (limit >= curEnd && start > curEnd) {
        writeSysfs(endPath, limit);
        writeSysfs(startPath, start);
    } else if (limit < curStart) {
        writeSysfs(startPath, start);
        writeSysfs(endPath, limit);
    } else {
        writeSysfs(endPath, limit);
        writeSysfs(startPath, start);
    }
}

function readRemoteAutoLoginUser() {
    const userName = readTextFile(REMOTE_AUTOLOGIN_USER_PATH);
    if (!userName)
        return null;
    return /^[a-z_][a-z0-9_-]*[$]?$/.test(userName) ? userName : null;
}

function isRemoteGreeter() {
    return Boolean(Main.sessionMode?.isGreeter) && GLib.getenv('GDM_SEAT_ID') !== 'seat0';
}

function isUserDesktopMode() {
    const mode = Main.sessionMode?.currentMode;
    return !Main.sessionMode?.isGreeter && mode !== 'unlock-dialog' && mode !== 'initial-setup';
}

function scheduleRemoteAutoLogin(ext, dialog) {
    if (!dialog || dialog._salamiRemoteAutoLoginDone || !isRemoteGreeter())
        return;
    const userName = readRemoteAutoLoginUser();
    if (!userName || ext._remoteAutoLoginIdleId)
        return;

    ext._remoteAutoLoginIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
        ext._remoteAutoLoginIdleId = 0;
        if (dialog._salamiRemoteAutoLoginDone || dialog._authPrompt?.visible)
            return GLib.SOURCE_REMOVE;
        const item = dialog._userList?.getItemFromUserName(userName);
        if (item) {
            dialog._salamiRemoteAutoLoginDone = true;
            dialog._onUserListActivated(item);
        }
        return GLib.SOURCE_REMOVE;
    });
}

function wakeGreeterShield(shield) {
    if (shield._becameActiveId !== 0) {
        shield.idleMonitor.remove_watch(shield._becameActiveId);
        shield._becameActiveId = 0;
    }
    shield._longLightbox.lightOff();
    shield._shortLightbox.lightOff();
    shield._lockDialogGroup.remove_all_transitions();
    shield._lockDialogGroup.translation_y = 0;
    shield._lockScreenState = MessageTray.State.HIDDEN;
    shield._lockScreenGroup.hide();
    shield._showPointer();
    shield.emit('wake-up-screen');
    shield._activationTime = 0;
    shield._setActive(false);
}

function guardModemItemPrototype(ext, item) {
    const proto = item ? Object.getPrototypeOf(item) : null;
    if (!proto || ext._modemItemProto)
        return;
    const desc = Object.getOwnPropertyDescriptor(proto, 'icon_name');
    if (!desc?.get)
        return;
    ext._modemItemProto = proto;
    ext._origModemIconNameDesc = desc;
    Object.defineProperty(proto, 'icon_name', {
        ...desc,
        get() {
            if (!this._mobileDevice)
                return 'network-cellular-acquiring-symbolic';
            return desc.get.call(this);
        },
    });
}

function guardModemToggle(ext, modemToggle) {
    if (!modemToggle)
        return;
    if (modemToggle._items instanceof Map) {
        for (const item of modemToggle._items.values()) {
            guardModemItemPrototype(ext, item);
            break;
        }
    }
    const toggleProto = Object.getPrototypeOf(modemToggle);
    if (!toggleProto?._createDeviceMenuItem || ext._modemToggleProto)
        return;
    const origCreate = toggleProto._createDeviceMenuItem;
    ext._modemToggleProto = toggleProto;
    ext._origCreateModemMenuItem = origCreate;
    toggleProto._createDeviceMenuItem = function (device) {
        if (!ext._modemItemProto && device) {
            Object.defineProperty(device, 'active_connection', {
                value: null,
                configurable: true,
            });
            let item;
            try {
                item = origCreate.call(this, device);
            } finally {
                delete device.active_connection;
            }
            guardModemItemPrototype(ext, item);
            item?._activeConnectionChanged?.();
            return item;
        }
        const item = origCreate.call(this, device);
        guardModemItemPrototype(ext, item);
        return item;
    };
}

const SalamiPerfMenuToggle = GObject.registerClass(
class SalamiPerfMenuToggle extends QuickSettings.QuickMenuToggle {
    _init() {
        super._init({
            title: '性能模式',
            iconName: 'power-profile-balanced-symbolic',
            toggleMode: false,
        });
        this.menu.setHeader('power-profile-balanced-symbolic', 'SoC 性能档位');
        this._modeItems = new Map();
        for (const entry of PERF_MODES) {
            const item = this.menu.addAction(entry.label, () => {
                this._selectMode(entry.id);
            });
            this._modeItems.set(entry.id, item);
        }
        this.connect('clicked', () => {
            const cur = detectPerfMode();
            const order = ['balanced', 'performance', 'eco'];
            const next = order[(order.indexOf(cur) + 1) % order.length];
            this._selectMode(next);
        });
        this.refreshState();
    }

    _selectMode(mode) {
        try {
            applyPerfMode(mode);
        } catch (e) {
            console.warn(`salami-osk-guard: failed to set perf mode: ${e}`);
        }
        this.refreshState();
    }

    refreshState() {
        const cur = detectPerfMode();
        const meta = PERF_MODES.find(m => m.id === cur) ?? PERF_MODES[1];
        this.iconName = meta.icon;
        this.subtitle = meta.short;
        this.checked = cur !== 'balanced';
        for (const [id, item] of this._modeItems.entries()) {
            item.setOrnament(id === cur
                ? PopupMenu.Ornament.CHECK
                : PopupMenu.Ornament.NONE);
        }
    }
});

const SalamiChargeToggle = GObject.registerClass(
class SalamiChargeToggle extends QuickSettings.QuickToggle {
    _init() {
        super._init({
            title: '80% 限充',
            iconName: 'battery-good-charging-symbolic',
            toggleMode: false,
        });
        this.connect('clicked', () => {
            const nextLimit = this.checked ? 100 : 80;
            try {
                setChargeThresholds(nextLimit);
            } catch (e) {
                console.warn(`salami-osk-guard: failed to set charge limit: ${e}`);
            }
            this.refreshState();
        });
        this.refreshState();
    }

    refreshState() {
        const end = readIntFile(`${BAT_DIR}/charge_control_end_threshold`, 80) ?? 80;
        const cap = readIntFile(`${BAT_DIR}/capacity`);
        const pUw = readIntFile(`${BAT_DIR}/power_now`, 0) ?? 0;
        const limited = end <= 80;
        this.checked = limited;
        this.iconName = limited
            ? 'battery-good-charging-symbolic'
            : 'battery-full-charged-symbolic';

        const watts = Math.abs(pUw) / 1000000;
        const capPrefix = cap !== null ? `${cap}% · ` : '';
        if (watts >= 0.5)
            this.subtitle = `${capPrefix}${watts.toFixed(1)} W`;
        else
            this.subtitle = `${capPrefix}${limited ? '护航 75–80%' : '100% 满充'}`;
    }
});

const SalamiTorchToggle = GObject.registerClass(
class SalamiTorchToggle extends QuickSettings.QuickToggle {
    _init() {
        super._init({
            title: '手电筒',
            iconName: 'display-brightness-symbolic',
            toggleMode: false,
        });
        this.connect('clicked', () => {
            const cur = readIntFile(`${TORCH_DIR}/brightness`, 0) ?? 0;
            const max = readIntFile(`${TORCH_DIR}/max_brightness`, 255) ?? 255;
            const next = cur > 0 ? 0 : Math.min(max, DEFAULT_TORCH_LEVEL);
            try {
                writeSysfs(`${TORCH_DIR}/brightness`, next);
            } catch (e) {
                console.warn(`salami-osk-guard: failed to toggle torch: ${e}`);
            }
            this.refreshState();
        });
        this.refreshState();
    }

    refreshState() {
        const cur = readIntFile(`${TORCH_DIR}/brightness`, 0) ?? 0;
        const active = cur > 0;
        this.checked = active;
        this.subtitle = active ? '已开启' : '已关闭';
    }
});

export default class SalamiOskGuardExtension extends Extension {
    _syncHardwareIndicator() {
        if (!isUserDesktopMode()) {
            this._teardownHardwareIndicator();
            return;
        }
        if (this._hwIndicator || this._hwInitIdleId)
            return;
        if (!GLib.file_test(BAT_DIR, GLib.FileTest.IS_DIR))
            return;

        const attach = () => {
            const qs = Main.panel?.statusArea?.quickSettings;
            if (!qs?.addExternalIndicator || !isUserDesktopMode())
                return false;
            const indicator = new QuickSettings.SystemIndicator();
            if (GLib.file_test(`${CPUFREQ_DIR}/policy0`, GLib.FileTest.IS_DIR)) {
                this._perfToggle = new SalamiPerfMenuToggle();
                indicator.quickSettingsItems.push(this._perfToggle);
            }
            this._chargeToggle = new SalamiChargeToggle();
            indicator.quickSettingsItems.push(this._chargeToggle);
            if (GLib.file_test(TORCH_DIR, GLib.FileTest.IS_DIR)) {
                this._torchToggle = new SalamiTorchToggle();
                indicator.quickSettingsItems.push(this._torchToggle);
            }
            qs.addExternalIndicator(indicator);
            this._hwIndicator = indicator;
            this._hwRefreshTimerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 15, () => {
                this._perfToggle?.refreshState();
                this._chargeToggle?.refreshState();
                this._torchToggle?.refreshState();
                return GLib.SOURCE_CONTINUE;
            });
            return true;
        };

        if (!attach()) {
            this._hwInitIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                this._hwInitIdleId = 0;
                attach();
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _teardownHardwareIndicator() {
        if (this._hwInitIdleId) {
            GLib.source_remove(this._hwInitIdleId);
            this._hwInitIdleId = 0;
        }
        if (this._hwRefreshTimerId) {
            GLib.source_remove(this._hwRefreshTimerId);
            this._hwRefreshTimerId = 0;
        }
        if (this._hwIndicator) {
            for (const item of this._hwIndicator.quickSettingsItems)
                item.destroy();
            this._hwIndicator.destroy();
            this._hwIndicator = null;
            this._perfToggle = null;
            this._chargeToggle = null;
            this._torchToggle = null;
        }
    }

    enable() {
        const keyboard = Main.keyboard;
        if (keyboard && !this._origMaybeHandleEvent) {
            const orig = keyboard.maybeHandleEvent;
            this._origMaybeHandleEvent = orig;
            keyboard.maybeHandleEvent = function (event) {
                if (!this._keyboard || !global.stage.get_event_actor(event))
                    return false;
                return orig.call(this, event);
            };
        }

        if (NetworkIndicator?.prototype?._init && !this._origNetworkInit) {
            const ext = this;
            const origNetInit = NetworkIndicator.prototype._init;
            this._origNetworkInit = origNetInit;
            NetworkIndicator.prototype._init = function (...args) {
                const ret = origNetInit.apply(this, args);
                guardModemToggle(ext, this._modemToggle);
                return ret;
            };
        }
        guardModemToggle(this, Main.panel?.statusArea?.quickSettings?._network?._modemToggle);

        if (LoginDialog?.prototype?._showPrompt && !this._origShowPrompt) {
            const origShowPrompt = LoginDialog.prototype._showPrompt;
            this._origShowPrompt = origShowPrompt;
            LoginDialog.prototype._showPrompt = function (...args) {
                this._setUserListExpanded(false);
                return origShowPrompt.apply(this, args);
            };

            const dialog = Main.screenShield?._dialog;
            if (dialog?._authPrompt?.visible && dialog?._userSelectionBox?.visible)
                dialog._setUserListExpanded(false);
        }

        if (LoginDialog?.prototype?._loadUserList && !this._origLoadUserList) {
            const ext = this;
            const origLoadUserList = LoginDialog.prototype._loadUserList;
            this._origLoadUserList = origLoadUserList;
            LoginDialog.prototype._loadUserList = function (...args) {
                const ret = origLoadUserList.apply(this, args);
                scheduleRemoteAutoLogin(ext, this);
                return ret;
            };

            const dialog = Main.screenShield?._dialog;
            if (dialog?._userListLoaded)
                scheduleRemoteAutoLogin(this, dialog);
        }

        if (ScreenShield?.prototype?.deactivate && !this._origDeactivate) {
            const origDeactivate = ScreenShield.prototype.deactivate;
            this._origDeactivate = origDeactivate;
            ScreenShield.prototype.deactivate = function (animate) {
                if (this._isGreeter || Main.sessionMode.isGreeter) {
                    wakeGreeterShield(this);
                    return;
                }
                return origDeactivate.call(this, animate);
            };
        }

        if (ScreenShield?.prototype?._continueDeactivate && !this._origContinueDeactivate) {
            const origContinueDeactivate = ScreenShield.prototype._continueDeactivate;
            this._origContinueDeactivate = origContinueDeactivate;
            ScreenShield.prototype._continueDeactivate = function (animate) {
                if (this._isGreeter || Main.sessionMode.isGreeter) {
                    wakeGreeterShield(this);
                    return;
                }
                return origContinueDeactivate.call(this, animate);
            };
        }

        if (ScreenShield?.prototype?._onUserBecameActive && !this._origOnUserBecameActive) {
            const origOnUserBecameActive = ScreenShield.prototype._onUserBecameActive;
            this._origOnUserBecameActive = origOnUserBecameActive;
            ScreenShield.prototype._onUserBecameActive = function () {
                if (this._isGreeter || Main.sessionMode.isGreeter) {
                    wakeGreeterShield(this);
                    return;
                }
                return origOnUserBecameActive.call(this);
            };
        }

        const shield = Main.screenShield;
        if (shield?._isGreeter && (shield._lockDialogGroup?.translation_y !== 0 || shield._isActive))
            wakeGreeterShield(shield);

        if (Main.sessionMode && !this._sessionModeUpdatedId) {
            this._sessionModeUpdatedId = Main.sessionMode.connect('updated', () => {
                this._syncHardwareIndicator();
            });
        }
        this._syncHardwareIndicator();
    }

    disable() {
        if (this._sessionModeUpdatedId && Main.sessionMode) {
            Main.sessionMode.disconnect(this._sessionModeUpdatedId);
            this._sessionModeUpdatedId = 0;
        }
        this._teardownHardwareIndicator();

        if (this._origMaybeHandleEvent && Main.keyboard) {
            Main.keyboard.maybeHandleEvent = this._origMaybeHandleEvent;
            this._origMaybeHandleEvent = null;
        }
        if (this._origNetworkInit && NetworkIndicator?.prototype) {
            NetworkIndicator.prototype._init = this._origNetworkInit;
            this._origNetworkInit = null;
        }
        if (this._modemToggleProto && this._origCreateModemMenuItem) {
            this._modemToggleProto._createDeviceMenuItem = this._origCreateModemMenuItem;
            this._modemToggleProto = null;
            this._origCreateModemMenuItem = null;
        }
        if (this._modemItemProto && this._origModemIconNameDesc) {
            Object.defineProperty(this._modemItemProto, 'icon_name', this._origModemIconNameDesc);
            this._modemItemProto = null;
            this._origModemIconNameDesc = null;
        }
        if (this._remoteAutoLoginIdleId) {
            GLib.source_remove(this._remoteAutoLoginIdleId);
            this._remoteAutoLoginIdleId = 0;
        }
        if (this._origLoadUserList && LoginDialog?.prototype) {
            LoginDialog.prototype._loadUserList = this._origLoadUserList;
            this._origLoadUserList = null;
        }
        if (this._origShowPrompt && LoginDialog?.prototype) {
            LoginDialog.prototype._showPrompt = this._origShowPrompt;
            this._origShowPrompt = null;
        }
        if (this._origDeactivate && ScreenShield?.prototype) {
            ScreenShield.prototype.deactivate = this._origDeactivate;
            this._origDeactivate = null;
        }
        if (this._origContinueDeactivate && ScreenShield?.prototype) {
            ScreenShield.prototype._continueDeactivate = this._origContinueDeactivate;
            this._origContinueDeactivate = null;
        }
        if (this._origOnUserBecameActive && ScreenShield?.prototype) {
            ScreenShield.prototype._onUserBecameActive = this._origOnUserBecameActive;
            this._origOnUserBecameActive = null;
        }
    }
}
