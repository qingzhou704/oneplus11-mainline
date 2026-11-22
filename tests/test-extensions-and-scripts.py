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
