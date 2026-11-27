#!/usr/bin/env python3
"""Offline static validation for GNOME Shell extensions, shell scripts, completion, and units."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
EXT_ROOT = REPO / "rootfs/salami-device/usr/share/gnome-shell/extensions"
COMPLETION = REPO / "rootfs/salami-device/usr/share/bash-completion/completions/salami-ctl"


class ExtensionsAndScriptsTests(unittest.TestCase):
    def test_gnome_shell_extensions_metadata_and_cleanup_invariants(self):
        exts = sorted(p for p in EXT_ROOT.iterdir() if p.is_dir())
        self.assertGreaterEqual(len(exts), 2)
        for ext_dir in exts:
            meta_path = ext_dir / "metadata.json"
            js_path = ext_dir / "extension.js"
            self.assertTrue(meta_path.is_file(), f"missing metadata.json in {ext_dir.name}")
            self.assertTrue(js_path.is_file(), f"missing extension.js in {ext_dir.name}")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta.get("uuid"), ext_dir.name)
            self.assertIn("50", meta.get("shell-version", []))
            self.assertTrue(meta.get("name"))

            js_src = js_path.read_text(encoding="utf-8")
            self.assertIn("export default class", js_src)
            self.assertIn("enable()", js_src)
            self.assertIn("disable()", js_src)

            # Every GLib.idle_add / GLib.timeout_add call must store its source ID for cleanup.
            for lineno, line in enumerate(js_src.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("GLib.idle_add(", "GLib.timeout_add(", "GLib.timeout_add_seconds(")):
                    self.fail(f"untracked GLib timer/idle source at {ext_dir.name}/extension.js:{lineno}")

            # Ensure balanced braces/parens at a lexical level and run node --check when available.
            if shutil.which("node"):
                # Replace GNOME Shell GI/resource URL imports with dummy specifiers only for syntax check.
                res = subprocess.run(
                    ["node", "--input-type=module", "--check"],
                    input=js_src,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(res.returncode, 0, f"JS syntax error in {ext_dir.name}: {res.stderr}")

        cc_js = (EXT_ROOT / "salami-control-center@oneplus11/extension.js").read_text(encoding="utf-8")
        self.assertIn("Gio.Cancellable", cc_js)
        self.assertIn("this._destroyed = true", cc_js)

        osk_js = (EXT_ROOT / "salami-osk-guard@oneplus11/extension.js").read_text(encoding="utf-8")
        self.assertIn("SALAMI_CTL", osk_js)
        self.assertNotIn("ECO_MAX_KHZ", osk_js)
        self.assertNotIn("setChargeThresholds", osk_js)

    def test_security_rules_and_ci_build_invariants(self):
        iris_rule = (REPO / "rootfs/salami-device/usr/lib/udev/rules.d/73-salami-iris-video.rules").read_text(encoding="utf-8")
        self.assertIn('MODE="0660"', iris_rule)
        self.assertNotIn('MODE="0666"', iris_rule)

        polkit_rule = (REPO / "rootfs/salami-device/usr/share/polkit-1/rules.d/51-salami-hardware-admin.rules").read_text(encoding="utf-8")
        self.assertIn('action.lookup("command_line")', polkit_rule)
        self.assertNotIn("service", polkit_rule.split("var allowed =", 1)[1])

        release_yml = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertNotIn('CROSS_COMPILE="ccache ', release_yml)
        self.assertIn('CROSS_COMPILE="aarch64-linux-gnu-"', release_yml)
        self.assertNotIn('lv="${{ inputs.', release_yml)
        self.assertNotIn('tag="${{ inputs.', release_yml)
        self.assertIn("tests/test-salami-ctl.py", release_yml)

        build_rootfs = (REPO / "tools/build-rootfs.sh").read_text(encoding="utf-8")
        self.assertIn("rtkit", build_rootfs)
        self.assertIn("mobile-broadband-provider-info", build_rootfs)

        build_kernel = (REPO / "tools/build-kernel.sh").read_text(encoding="utf-8")
        self.assertNotIn('>> "$b/arch/arm64/boot/Image"', build_kernel)
        self.assertIn("Image-dtb", build_kernel)

        build_initramfs = (REPO / "tools/build-full-initramfs.sh").read_text(encoding="utf-8")
        self.assertIn('command -v xz', build_initramfs)

        desktop_custom = (REPO / "tools/desktop-customize.sh").read_text(encoding="utf-8")
        self.assertIn("ssh@.service.d/50-salami-hostkeys.conf", desktop_custom)

        build_deb = (REPO / "tools/build-device-deb.sh").read_text(encoding="utf-8")
        self.assertIn("DEBIAN/conffiles", build_deb)

        self.assertFalse(
            (REPO / "rootfs/salami-device/usr/lib/systemd/system/cloudflared.service.d").exists(),
            "cloudflared drop-in should not remain in public salami-device package",
        )

    def test_posix_shell_scripts_syntax(self):
        sh_files: list[Path] = []
        sh_files.extend(sorted((REPO / "tools").glob("*.sh")))
        sh_files.extend(sorted((REPO / "tests").glob("*.sh")))
        for rel in (
            "initramfs/init",
            "rootfs/salami-device/DEBIAN/postinst",
            "rootfs/salami-device/DEBIAN/prerm",
            "rootfs/salami-device/usr/lib/salami/usb-gadget",
            "rootfs/salami-device/usr/lib/salami/ufs-tune",
            "rootfs/salami-device/usr/lib/salami/import-modem-data",
            "rootfs/salami-device/etc/NetworkManager/dispatcher.d/90-salami-wifi-powersave",
        ):
            p = REPO / rel
            if p.is_file():
                sh_files.append(p)

        self.assertGreaterEqual(len(sh_files), 10)
        for script in sh_files:
            res = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(
                res.returncode,
                0,
                f"sh -n failed for {script.relative_to(REPO)}: {res.stderr}",
            )

    def test_bash_completion_syntax_and_subcommand_coverage(self):
        self.assertTrue(COMPLETION.is_file(), "missing bash completion for salami-ctl")
        if shutil.which("bash"):
            res = subprocess.run(["bash", "-n", str(COMPLETION)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"bash -n failed: {res.stderr}")
        text = COMPLETION.read_text(encoding="utf-8")
        for subcmd in ("status", "watch", "doctor", "perf", "screen", "refresh", "hbm", "vooc", "touch", "modem", "security", "charge"):
            self.assertIn(subcmd, text, f"subcommand {subcmd!r} missing from bash completion")

    def test_systemd_units_and_udev_rules_sanity(self):
        unit_dirs = (
            REPO / "rootfs/salami-device/usr/lib/systemd/system",
            REPO / "rootfs/salami-device/usr/lib/systemd/user",
        )
        unit_count = 0
        for udir in unit_dirs:
            if not udir.is_dir():
                continue
            for p in sorted(udir.iterdir()):
                if p.is_file() and p.suffix in (".service", ".timer", ".socket"):
                    unit_count += 1
                    content = p.read_text(encoding="utf-8")
                    self.assertIn("[Unit]", content, f"missing [Unit] in {p.name}")
        self.assertGreaterEqual(unit_count, 5)

        udev_dir = REPO / "rootfs/salami-device/usr/lib/udev/rules.d"
        rules = sorted(udev_dir.glob("*.rules"))
        self.assertGreaterEqual(len(rules), 5)
        for rule_file in rules:
            for lineno, line in enumerate(rule_file.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                self.assertEqual(s.count('"') % 2, 0, f"unmatched quotes in {rule_file.name}:{lineno}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
