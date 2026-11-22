#!/usr/bin/env python3
"""Offline desktop-rootfs contract tests; no chroot, network or device access."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parents[1] / "tools/verify-desktop-rootfs.py"
spec = importlib.util.spec_from_file_location("desktop_verifier", SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class RootfsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir()
        self.manifest = Path(self.temp.name) / "packages.txt"
        self.manifest.write_text("# distribution packages\ngdm3\ngnome-shell # desktop\n", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(verifier, "PACKAGES_FILE", self.manifest).start()
        self.packages = {p: ("install ok installed", "1.0") for p in
                         ("gdm3", "gnome-shell", "firefox", "firefox-l10n-zh-cn",
                          "salami-device", "rmtfs", "linux-image-6.19-test")}
        self.status()
        self.put("etc/passwd", "root:x:0:0:root:/root:/bin/bash\ngdm:x:120:120::/var/lib/gdm3:/usr/sbin/nologin\ngnome-initial-setup:x:121:121::/run/gnome-initial-setup:/bin/false\n")
        self.put("etc/shadow", "root:!:1:0:99999:7:::\ngdm:*:1:0:99999:7:::\ngnome-initial-setup:!!:1:0:99999:7:::\n")
        self.put("etc/machine-id", "")
        self.put("etc/gdm3/custom.conf", "[daemon]\nInitialSetupEnable=true\n")
        self.put("usr/lib/systemd/system/graphical.target", "[Unit]\nDescription=Graphical\n")
        self.link("etc/systemd/system/default.target", "/usr/lib/systemd/system/graphical.target")
        self.put("boot/boot.img-6.19-test", "boot")
        self.put("usr/lib/modules/6.19-test/modules.dep", "")
        self.link("lib", "usr/lib")
        self.put("usr/bin/firefox", "#!/bin/sh\n")
        self.put("usr/libexec/gnome-initial-setup", "binary")
        for name in ("ucm.conf", "lib/card-init.conf", "lib/ctl-remap.conf"):
            self.put(f"usr/share/alsa/ucm2/{name}", "Syntax 6\n")
        for name in ("firefox", "org.gnome.Nautilus", "org.gnome.Console", "org.gnome.Settings",
                     "org.gnome.TextEditor", "org.gnome.Papers", "org.gnome.Loupe", "org.gnome.Showtime"):
            self.put(f"usr/share/applications/{name}.desktop", "[Desktop Entry]\nType=Application\nName=Test\nExec=test\n")

    def put(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")

    def link(self, path, target):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(target)

    def status(self):
        self.put("var/lib/dpkg/status", "\n".join(
            f"Package: {p}\nStatus: {s}\nVersion: {v}\nArchitecture: arm64\n"
            for p, (s, v) in self.packages.items()))

    def errors(self, fragment):
        errors = verifier.verify(self.root)
        self.assertTrue(any(fragment.lower() in e.lower() for e in errors), errors)

    def test_clean_root(self):
        self.assertEqual([], verifier.verify(self.root))

    def test_normal_user(self):
        for uid in (1000, 59999):
            with self.subTest(uid=uid):
                self.put("etc/passwd", f"root:x:0:0::/root:/bin/bash\nowner:x:{uid}:1000::/home/owner:/bin/bash\n")
                self.errors("ordinary user")

    def test_ucm_includes_required(self):
        (self.root / "usr/share/alsa/ucm2/lib/card-init.conf").unlink()
        self.errors("UCM")

    def test_missing_firefox(self):
        del self.packages["firefox"]
        self.status()
        self.errors("firefox")

    def test_manifest_required_package(self):
        self.manifest.write_text("gdm3\nmissing-package\n", encoding="utf-8")
        self.errors("missing-package")

    def test_missing_manifest_fails_closed(self):
        self.manifest.unlink()
        self.errors("package manifest")

    def test_uninstalled_or_broken_packages(self):
        for state in ("install ok unpacked", "install reinstreq installed", "install ok half-configured", "install ok triggers-pending"):
            with self.subTest(state=state):
                self.packages["unrelated"] = (state, "1")
                self.status()
                self.errors("dpkg")

    def test_pending_dpkg_updates(self):
        self.put("var/lib/dpkg/updates/0000", "pending transaction")
        self.errors("dpkg")

    def test_snap_and_transitional_firefox(self):
        self.packages["snapd"] = ("install ok installed", "2")
        self.status()
        self.errors("snapd")
        del self.packages["snapd"]
        self.packages["firefox"] = ("install ok installed", "1:1snap1-0ubuntu1")
        self.status()
        self.errors("snap")

    def test_usable_passwords(self):
        for password in ("", "$y$hash", "$6$hash", "plaintext"):
            with self.subTest(password=password):
                self.put("etc/shadow", f"root:{password}:1:0:99999:7:::\n")
                self.errors("password")

    def test_missing_identity_files(self):
        for path in ("etc/passwd", "etc/shadow", "etc/machine-id"):
            with self.subTest(path=path):
                old = (self.root / path).read_text()
                (self.root / path).unlink()
                self.errors(path)
                self.put(path, old)

    def test_sudo_nopasswd(self):
        self.put("etc/sudoers.d/owner", "owner ALL=(ALL) NOPASSWD: ALL\n")
        self.errors("NOPASSWD")

    def test_empty_opt_in_group_policy_allowed(self):
        self.packages['salami-desktop-passwordless'] = ('install ok installed', '0.1')
        self.status()
        self.put('etc/group', 'root:x:0:\nsalami-passwordless:x:990:\n')
        self.put('etc/sudoers.d/50-salami-passwordless',
                 '%salami-passwordless ALL=(ALL:ALL) NOPASSWD: ALL\n')
        self.assertEqual([], verifier.verify(self.root))
        self.put('etc/group', 'root:x:0:\nsalami-passwordless:x:990:root\n')
        self.errors('NOPASSWD')

    def test_opt_in_policy_without_package_rejected(self):
        self.put('etc/group', 'salami-passwordless:x:990:\n')
        self.put('etc/sudoers.d/50-salami-passwordless',
                 '%salami-passwordless ALL=(ALL:ALL) NOPASSWD: ALL\n')
        self.errors('NOPASSWD')

    def test_numeric_uid_sudo_nopasswd(self):
        self.put("etc/sudoers", "#1000 ALL=(ALL) NOPASSWD: ALL\n")
        self.errors("NOPASSWD")

    def test_commented_sudo_policy_allowed(self):
        self.put("etc/sudoers", "# example NOPASSWD: ALL\n%admin ALL=(ALL) ALL\n")
        self.assertEqual([], verifier.verify(self.root))

    def test_private_artifacts(self):
        for path in ("etc/ssh/ssh_host_ed25519_key", "root/.ssh/authorized_keys", "opt/user/authorized_keys",
                     "home/owner/.config/test", "etc/NetworkManager/system-connections/wifi.nmconnection",
                     "var/lib/iwd/Home.psk", "etc/wpa_supplicant/wpa_supplicant.conf"):
            with self.subTest(path=path):
                self.put(path, "private")
                self.errors("private")
                (self.root / path).unlink()
                parent = (self.root / path).parent
                while parent != self.root and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                self.assertEqual([], verifier.verify(self.root))

    def test_machine_identity(self):
        self.put("etc/machine-id", "123456\n")
        self.errors("machine-id")

    def test_dbus_identity(self):
        self.put("var/lib/dbus/machine-id", "old-machine\n")
        self.errors("machine-id")

    def test_gdm_firstboot_required(self):
        for config in ("[daemon]\nInitialSetupEnable=false\n", "[security]\nInitialSetupEnable=true\n",
                       "[daemon]\nInitialSetupEnable=true\nAutomaticLoginEnable=true\n"):
            with self.subTest(config=config):
                self.put("etc/gdm3/custom.conf", config)
                self.errors("GDM")

    def test_graphical_link_required(self):
        (self.root / "etc/systemd/system/default.target").unlink()
        self.put("etc/systemd/system/default.target", "graphical.target")
        self.errors("graphical.target")

    def test_remote_enablement(self):
        for unit in ("ssh.service", "ssh.socket", "sshd.service", "xrdp.service", "gnome-remote-desktop.service", "salami-debug-shell.socket"):
            with self.subTest(unit=unit):
                path = f"etc/systemd/system/multi-user.target.wants/{unit}"
                self.link(path, f"/usr/lib/systemd/system/{unit}")
                self.errors("enabled")
                (self.root / path).unlink()

    def test_vendor_user_remote_enablement(self):
        self.link("usr/lib/systemd/user/graphical-session.target.wants/gnome-remote-desktop.service", "../gnome-remote-desktop.service")
        self.errors("enabled")

    def test_missing_or_mismatched_modules(self):
        (self.root / "usr/lib/modules/6.19-test").rename(self.root / "usr/lib/modules/6.18-other")
        self.errors("modules")

    def test_missing_modules(self):
        (self.root / "usr/lib/modules/6.19-test").rename(Path(self.temp.name) / "removed-modules")
        self.errors("missing kernel modules")

    def test_extra_modules_release(self):
        self.put("usr/lib/modules/6.18-other/modules.dep", "")
        self.errors("modules release")

    def test_empty_package_manifest(self):
        self.manifest.write_text("# no packages\n", encoding="utf-8")
        self.errors("package manifest")

    def test_multiple_boot_images(self):
        self.put("boot/boot.img-other", "boot")
        self.errors("boot.img")

    def test_missing_kernel_package(self):
        del self.packages["linux-image-6.19-test"]
        self.status()
        self.errors("linux-image")

    def test_desktop_and_binaries_required(self):
        for path in ("usr/share/applications/firefox.desktop", "usr/share/applications/org.gnome.Papers.desktop",
                     "usr/bin/firefox", "usr/libexec/gnome-initial-setup"):
            with self.subTest(path=path):
                old = (self.root / path).read_text()
                (self.root / path).unlink()
                self.errors("missing")
                self.put(path, old)

    def test_build_policy_removed(self):
        self.put("usr/sbin/policy-rc.d", "exit 101\n")
        self.errors("policy-rc.d")

    def test_absolute_binary_and_dbus_symlinks(self):
        (self.root / "usr/bin/firefox").unlink()
        self.put("usr/lib/firefox/firefox", "binary")
        self.link("usr/bin/firefox", "/usr/lib/firefox/firefox")
        self.link("var/lib/dbus/machine-id", "/etc/machine-id")
        self.assertEqual([], verifier.verify(self.root))

    def test_symlink_loop_returns_errors(self):
        (self.root / "etc/machine-id").unlink()
        self.link("etc/machine-id", "/etc/machine-id")
        self.errors("symlink loop")

    def test_pending_triggers(self):
        self.put("var/lib/dpkg/triggers/Unincorp", "trigger pending\n")
        self.errors("triggers")

    def test_malformed_dpkg_status(self):
        self.put("var/lib/dpkg/status", "Package: firefox\ninvalid-line\n")
        self.errors("dpkg")

    def test_masks_and_disabled_units_allowed(self):
        self.link("etc/systemd/system/ssh.service", "/dev/null")
        self.put("usr/lib/systemd/system/salami-debug-shell.socket", "[Socket]\nListenStream=23\n")
        self.assertEqual([], verifier.verify(self.root))

    def test_removed_package_and_held_installed_allowed(self):
        self.packages["old-package"] = ("deinstall ok config-files", "1")
        self.packages["firefox"] = ("hold ok installed", "150")
        self.status()
        self.assertEqual([], verifier.verify(self.root))

    def test_alternate_real_desktop_paths(self):
        for old, new in (("org.gnome.Console", "org.gnome.Terminal"),
                         ("org.gnome.Settings", "gnome-control-center"),
                         ("org.gnome.Papers", "org.gnome.Evince"),
                         ("org.gnome.Loupe", "org.gnome.eog"),
                         ("org.gnome.Showtime", "org.gnome.Totem")):
            (self.root / f"usr/share/applications/{old}.desktop").rename(
                self.root / f"usr/share/applications/{new}.desktop")
        self.put("usr/lib/gnome-initial-setup/gnome-initial-setup", "binary")
        (self.root / "usr/libexec/gnome-initial-setup").unlink()
        self.assertEqual([], verifier.verify(self.root))

    def test_cli_success_and_policy_failure(self):
        # Run the real main() in another interpreter with only its manifest
        # location redirected; the production CLI has no policy override.
        code = ("import importlib.util,pathlib,sys;"
                "s=importlib.util.spec_from_file_location('v',sys.argv[1]);"
                "v=importlib.util.module_from_spec(s);s.loader.exec_module(v);"
                "v.PACKAGES_FILE=pathlib.Path(sys.argv[2]);"
                "sys.argv=[sys.argv[1],sys.argv[3]];raise SystemExit(v.main())")
        command = [sys.executable, "-B", "-c", code, str(SCRIPT), str(self.manifest), str(self.root)]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline checks passed", result.stdout)
        self.put("etc/machine-id", "not-clean")
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("machine-id", result.stderr)

    def test_cli_rejects_bad_root(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), str(self.root / "absent")], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root", result.stderr.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
