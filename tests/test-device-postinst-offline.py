#!/usr/bin/env python3
"""Run the postinst control flow with harmless mocked commands, never device code."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

SOURCE = Path(__file__).resolve().parents[1] / 'rootfs/salami-device/DEBIAN/postinst'


class OfflinePostinst(unittest.TestCase):
    def _run_offline(self, action, prev_version):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / 'calls'
            log.touch()
            script = SOURCE.read_text()
            # Exercise the real script branches without requiring the package installed
            # on the host, and force the offline environment predicate.
            script = script.replace('/usr/lib/salami/wifi-board', 'wifi-board')
            script = script.replace('[ -d /run/systemd/system ]', 'false')
            candidate = root / 'postinst'
            candidate.write_text(script)
            commands = {
                'wifi-board': 'exit 0',
                'systemctl': 'echo "$*" >> "$CALLS"; case "$1" in start|restart|reload*|daemon-reload) exit 91;; esac',
                'udevadm': 'echo udevadm >> "$CALLS"; exit 92',
                'journalctl': 'echo journalctl >> "$CALLS"; exit 93',
                'modprobe': 'echo modprobe >> "$CALLS"; exit 94',
                'sysctl': 'echo sysctl >> "$CALLS"; exit 95',
            }
            for name, body in commands.items():
                path = root / name
                path.write_text('#!/bin/sh\n' + body + '\n')
                path.chmod(0o755)
            env = dict(os.environ, PATH=f'{root}:/usr/bin:/bin', CALLS=str(log))
            result = subprocess.run(['sh', str(candidate), action, prev_version], env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return log.read_text()

    def test_offline_configure_enables_without_runtime_operations(self):
        calls = self._run_offline('configure', '')
        self.assertIn('enable salami-usb-gadget.service', calls)
        self.assertIn('enable salami-import-gpu-firmware.service', calls)
        self.assertIn('enable salami-power-key.service', calls)
        self.assertIn('enable systemd-oomd.service fstrim.timer', calls)
        self.assertIn('enable irqbalance.service', calls)
        self.assertIn('enable salami-ufs-tune.service salami-modem-guard.timer', calls)
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_029_has_no_runtime_operations(self):
        calls = self._run_offline('configure', '0.29')
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_030_has_no_runtime_operations(self):
        calls = self._run_offline('configure', '0.30')
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_032_has_no_runtime_operations(self):
        calls = self._run_offline('configure', '0.32')
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('journalctl', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_033_has_no_runtime_operations(self):
        calls = self._run_offline('configure', '0.33')
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('modprobe', calls)
        self.assertNotIn('sysctl', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_034_enables_oomd_without_runtime_operations(self):
        calls = self._run_offline('configure', '0.34')
        self.assertIn('enable systemd-oomd.service fstrim.timer', calls)
        self.assertIn('enable irqbalance.service', calls)
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_035_enables_irqbalance_without_runtime_operations(self):
        calls = self._run_offline('configure', '0.35')
        self.assertIn('enable irqbalance.service', calls)
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('sysctl', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_037_has_no_runtime_operations(self):
        calls = self._run_offline('configure', '0.37')
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('sysctl', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)

    def test_offline_upgrade_from_044_has_no_runtime_operations(self):
        calls = self._run_offline('configure', '0.44')
        self.assertNotIn('udevadm', calls)
        self.assertNotIn('sysctl', calls)
        self.assertNotIn('daemon-reload', calls)
        self.assertNotIn('start ', calls)
        self.assertNotIn('restart ', calls)


if __name__ == '__main__':
    unittest.main(verbosity=2)
