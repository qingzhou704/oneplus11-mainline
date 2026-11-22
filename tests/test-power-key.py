#!/usr/bin/env python3
"""Unit tests for the salami power-key short/long press controller and OSK guard."""
from importlib.machinery import SourceFileLoader
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1] / "rootfs/salami-device/usr/lib/salami/power-key"
spec = importlib.util.spec_from_loader("salami_power_key", SourceFileLoader("salami_power_key", str(SOURCE)))
power_key = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power_key)


class FakeBackend:
    def __init__(self, *, screen_off: bool) -> None:
        self.screen_off = screen_off
        self.calls: list[str] = []

    def is_screen_off(self) -> bool:
        self.calls.append("is_screen_off")
        return self.screen_off

    def wake_screen(self) -> None:
        self.calls.append("wake_screen")
        self.screen_off = False

    def blank_screen(self) -> None:
        self.calls.append("blank_screen")
        self.screen_off = True

    def prompt_power_off(self) -> None:
        self.calls.append("prompt_power_off")


class PowerKeyControllerTests(unittest.TestCase):
    def test_short_press_while_screen_on_blanks_on_release(self):
        backend = FakeBackend(screen_off=False)
        ctrl = power_key.PowerKeyController(backend, long_press_s=0.75)

        ctrl.on_key_event(1, 10.00)
        self.assertEqual(ctrl.next_deadline(), 10.75)
        self.assertEqual(backend.calls, ["is_screen_off"])

        ctrl.on_key_event(0, 10.12)
        self.assertIsNone(ctrl.next_deadline())
        self.assertEqual(backend.calls, ["is_screen_off", "blank_screen"])
        self.assertTrue(backend.screen_off)

    def test_short_press_while_screen_off_wakes_on_press_and_keeps_on_release(self):
        backend = FakeBackend(screen_off=True)
        ctrl = power_key.PowerKeyController(backend, long_press_s=0.75)

        ctrl.on_key_event(1, 20.00)
        self.assertEqual(ctrl.next_deadline(), 20.75)
        self.assertEqual(backend.calls, ["is_screen_off", "wake_screen"])
        self.assertFalse(backend.screen_off)

        ctrl.on_key_event(0, 20.15)
        self.assertIsNone(ctrl.next_deadline())
        self.assertEqual(backend.calls, ["is_screen_off", "wake_screen"])
        self.assertFalse(backend.screen_off)

    def test_long_press_while_screen_on_prompts_poweroff_and_release_does_not_blank(self):
        backend = FakeBackend(screen_off=False)
        ctrl = power_key.PowerKeyController(backend, long_press_s=0.75)

        ctrl.on_key_event(1, 30.00)
        ctrl.on_timeout(30.75)
        self.assertIsNone(ctrl.next_deadline())
        self.assertEqual(backend.calls, ["is_screen_off", "prompt_power_off"])

        ctrl.on_key_event(0, 31.10)
        self.assertEqual(backend.calls, ["is_screen_off", "prompt_power_off"])
        self.assertFalse(backend.screen_off)

    def test_long_press_while_screen_off_wakes_then_prompts_poweroff(self):
        backend = FakeBackend(screen_off=True)
        ctrl = power_key.PowerKeyController(backend, long_press_s=0.75)

        ctrl.on_key_event(1, 40.00)
        ctrl.on_timeout(40.75)
        self.assertIsNone(ctrl.next_deadline())
        self.assertEqual(backend.calls, ["is_screen_off", "wake_screen", "prompt_power_off"])

        ctrl.on_key_event(0, 41.00)
        self.assertEqual(backend.calls, ["is_screen_off", "wake_screen", "prompt_power_off"])
        self.assertFalse(backend.screen_off)

    def test_autorepeat_and_stray_release_are_ignored(self):
        backend = FakeBackend(screen_off=False)
        ctrl = power_key.PowerKeyController(backend, long_press_s=0.75)

        ctrl.on_key_event(0, 1.00)
        ctrl.on_key_event(2, 1.10)
        self.assertEqual(backend.calls, [])
        self.assertIsNone(ctrl.next_deadline())

        ctrl.on_key_event(1, 2.00)
        ctrl.on_key_event(2, 2.50)
        self.assertEqual(backend.calls, ["is_screen_off"])
        ctrl.on_timeout(2.75)
        ctrl.on_key_event(2, 2.85)
        ctrl.on_key_event(0, 2.95)
        self.assertEqual(backend.calls, ["is_screen_off", "prompt_power_off"])


class FakeWakeEmitter:
    def __init__(self) -> None:
        self.count = 0

    def emit_wakeup(self) -> None:
        self.count += 1


class Seat0GnomeBackendTests(unittest.TestCase):
    def test_wake_screen_emits_wakeup_and_sets_power_save_without_screensaver_deactivate(self):
        emitter = FakeWakeEmitter()
        backend = power_key.Seat0GnomeBackend(wake_emitter=emitter)
        calls: list[tuple[int, tuple[str, ...]]] = []

        backend.get_seat0_graphical_uid = lambda: 60584  # type: ignore[method-assign]

        def fake_run_user_busctl(uid: int, *args: str):
            calls.append((uid, args))
            return None

        backend.run_user_busctl = fake_run_user_busctl  # type: ignore[method-assign]
        backend.wake_screen()

        self.assertEqual(emitter.count, 1)
        self.assertEqual(
            calls,
            [
                (
                    60584,
                    (
                        "set-property",
                        "org.gnome.Mutter.DisplayConfig",
                        "/org/gnome/Mutter/DisplayConfig",
                        "org.gnome.Mutter.DisplayConfig",
                        "PowerSaveMode",
                        "i",
                        "0",
                    ),
                )
            ],
        )
        for _uid, args in calls:
            self.assertNotIn("org.gnome.ScreenSaver", args)
            self.assertNotIn("SetActive", args)


class OskGuardExtensionTests(unittest.TestCase):
    def test_extension_metadata_schema_and_guard(self):
        pkg_root = Path(__file__).resolve().parents[1] / "rootfs/salami-device"
        ext_dir = pkg_root / "usr/share/gnome-shell/extensions/salami-osk-guard@oneplus11"
        metadata = json.loads((ext_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["uuid"], "salami-osk-guard@oneplus11")
        self.assertEqual(metadata["uuid"], ext_dir.name)
        self.assertIn("50", metadata["shell-version"])
        self.assertEqual(
            set(metadata["session-modes"]),
            {"user", "ubuntu", "unlock-dialog", "gdm", "initial-setup"},
        )

        override = (pkg_root / "usr/share/glib-2.0/schemas/50-salami-osk-guard.gschema.override").read_text(
            encoding="utf-8"
        )
        self.assertIn("[org.gnome.shell]", override)
        self.assertIn("salami-osk-guard@oneplus11", override)

        js = (ext_dir / "extension.js").read_text(encoding="utf-8")
        self.assertIn("get_event_actor", js)
        self.assertIn("LoginDialog", js)
        self.assertIn("_showPrompt", js)
        self.assertIn("_setUserListExpanded(false)", js)
        self.assertIn("this._origShowPrompt", js)
        self.assertIn("ScreenShield", js)
        self.assertIn("ScreenShield.prototype.deactivate", js)
        self.assertIn("this._origDeactivate", js)
        self.assertIn("_continueDeactivate", js)
        self.assertIn("this._origContinueDeactivate", js)
        self.assertIn("_onUserBecameActive", js)
        self.assertIn("this._origOnUserBecameActive", js)
        self.assertIn("translation_y = 0", js)
        self.assertIn("_longLightbox.lightOff()", js)
        self.assertIn("disable()", js)
        self.assertIn("this._origMaybeHandleEvent", js)
        self.assertIn("/etc/salami/remote-autologin-user", js)
        self.assertIn("GDM_SEAT_ID", js)
        self.assertIn("this._origLoadUserList", js)
        self.assertIn("_onUserListActivated", js)
        self.assertIn("NetworkIndicator", js)
        self.assertIn("guardModemToggle", js)
        self.assertIn("_origModemIconNameDesc", js)
        self.assertIn("SalamiPerfMenuToggle", js)
        self.assertIn("SalamiChargeToggle", js)
        self.assertIn("SalamiTorchToggle", js)
        self.assertIn("IOChannel.new_file", js)
        self.assertNotIn("file_set_contents", js)


class TouchPolicySyncTests(unittest.TestCase):
    def test_touch_policy_sync_follows_dsi_dpms_and_off_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            pm = r / "power_mode"
            pol = r / "off_policy"
            dsi = r / "drm" / "card1-DSI-1" / "dpms"
            dsi.parent.mkdir(parents=True, exist_ok=True)
            pm.write_text("active\n", encoding="utf-8")
            pol.write_text("gesture\n", encoding="utf-8")
            dsi.write_text("Off\n", encoding="utf-8")

            sync = power_key.TouchPolicySync(
                power_mode_param=pm,
                off_policy_file=pol,
                drm_dir=r / "drm",
            )
            interval = sync.poll_sync()
            self.assertEqual(interval, 1.0)
            self.assertEqual(pm.read_text(encoding="utf-8").strip(), "gesture")

            dsi.write_text("On\n", encoding="utf-8")
            interval2 = sync.poll_sync()
            self.assertEqual(interval2, 3.0)
            self.assertEqual(pm.read_text(encoding="utf-8").strip(), "active")

            pol.write_text("sleep\n", encoding="utf-8")
            sync.apply_for_screen_off(True, force=True)
            self.assertEqual(pm.read_text(encoding="utf-8").strip(), "sleep")


class EventLoopSignalTests(unittest.TestCase):
    def test_sigterm_wakes_blocking_event_loop_immediately(self):
        r_fd, w_fd = os.pipe()
        os.set_blocking(r_fd, False)
        pid = os.fork()
        if pid == 0:
            os.close(w_fd)
            try:
                ctrl = power_key.PowerKeyController(FakeBackend(screen_off=False))
                rc = power_key.run_event_loop(r_fd, ctrl)
            finally:
                os.close(r_fd)
            os._exit(rc)

        os.close(r_fd)
        try:
            select.select([], [], [], 0.1)
            t0 = time.monotonic()
            os.kill(pid, signal.SIGTERM)
            deadline = t0 + 1.5
            status = None
            while time.monotonic() < deadline:
                waited_pid, st = os.waitpid(pid, os.WNOHANG)
                if waited_pid == pid:
                    status = st
                    break
                select.select([], [], [], 0.02)
            if status is None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                self.fail("run_event_loop did not exit promptly on SIGTERM")
            self.assertTrue(os.WIFEXITED(status), f"unexpected wait status {status}")
            self.assertEqual(os.WEXITSTATUS(status), 0)
            self.assertLess(time.monotonic() - t0, 1.0)
        finally:
            os.close(w_fd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
