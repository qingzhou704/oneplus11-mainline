#!/usr/bin/env python3
"""Offline unit tests for import-gpu-firmware (fresh, upgrade, and skip paths)."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SOURCE = (
    Path(__file__).resolve().parents[1]
    / "rootfs/salami-device/usr/lib/salami/import-gpu-firmware"
)


def load_module():
    loader = SourceFileLoader("import_gpu_firmware_under_test", str(SOURCE))
    spec = spec_from_loader(loader.name, loader)
    mod = module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class ImportVendorFirmwareTest(unittest.TestCase):
    def _run_with_mock_vendor(self, tmp, fw_dir, vendor_payloads):
        mod = load_module()
        super_file = tmp / "super.img"
        super_file.write_bytes(b"mock-super")
        vendor_tree = tmp / "vendor_src"
        for rel, data in vendor_payloads.items():
            p = vendor_tree / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

        mount_base = tmp / "run"
        mount_base.mkdir(exist_ok=True)
        cmds = []
        real_mkdtemp = tempfile.mkdtemp

        def fake_mkdtemp(prefix="", dir=None):
            return real_mkdtemp(prefix=prefix, dir=str(mount_base))

        def fake_run(cmd, check=False):
            cmds.append(list(cmd))
            if cmd[:2] == ["mount", "-t"]:
                mp = Path(cmd[-1])
                shutil.copytree(vendor_tree, mp, dirs_exist_ok=True)
            elif cmd[:1] == ["umount"]:
                mp = Path(cmd[-1])
                for child in list(mp.iterdir()):
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            return mock.Mock(returncode=0)

        mod.SUPER = str(super_file)
        mod.FIRMWARE_DIR = fw_dir
        with mock.patch.object(mod, "read_vendor_table", return_value="0 8 linear /dev/loop0 0"), \
             mock.patch.object(mod.tempfile, "mkdtemp", side_effect=fake_mkdtemp), \
             mock.patch.object(mod.subprocess, "run", side_effect=fake_run):
            mod.main()
        return cmds

    def test_fresh_copies_both_firmwares_atomically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fw_dir = tmp / "fw/qcom/sm8550/oneplus/salami"
            payloads = {
                "firmware/a740_zap.mbn": b"ZAP_BYTES_066",
                "firmware/vpu30_4v.mbn": b"IRIS_VPU30_066",
            }
            cmds = self._run_with_mock_vendor(tmp, fw_dir, payloads)
            self.assertEqual([c[0] for c in cmds], ["dmsetup", "mount", "umount", "dmsetup"])
            for rel, expected in payloads.items():
                dest = fw_dir / Path(rel).name
                self.assertEqual(dest.read_bytes(), expected)
                self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o644)
            hidden = [p for p in fw_dir.iterdir() if p.name.startswith(".")]
            self.assertEqual(hidden, [])

    def test_upgrade_copies_only_missing_video_firmware(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fw_dir = tmp / "fw/qcom/sm8550/oneplus/salami"
            fw_dir.mkdir(parents=True)
            zap = fw_dir / "a740_zap.mbn"
            zap.write_bytes(b"EXISTING_ZAP_SENTINEL")
            payloads = {
                "firmware/a740_zap.mbn": b"SHOULD_NOT_OVERWRITE",
                "firmware/vpu30_4v.mbn": b"NEW_VPU30_BYTES",
            }
            cmds = self._run_with_mock_vendor(tmp, fw_dir, payloads)
            self.assertEqual([c[0] for c in cmds], ["dmsetup", "mount", "umount", "dmsetup"])
            self.assertEqual(zap.read_bytes(), b"EXISTING_ZAP_SENTINEL")
            vpu = fw_dir / "vpu30_4v.mbn"
            self.assertEqual(vpu.read_bytes(), b"NEW_VPU30_BYTES")
            self.assertEqual(stat.S_IMODE(vpu.stat().st_mode), 0o644)

    def test_skips_opening_super_when_both_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fw_dir = tmp / "fw/qcom/sm8550/oneplus/salami"
            fw_dir.mkdir(parents=True)
            (fw_dir / "a740_zap.mbn").write_bytes(b"zap")
            (fw_dir / "vpu30_4v.mbn").write_bytes(b"vpu")
            mod = load_module()
            mod.FIRMWARE_DIR = fw_dir
            mod.SUPER = str(tmp / "nonexistent-super-must-not-open")
            with mock.patch.object(mod, "read_vendor_table") as m_tbl:
                mod.main()
            m_tbl.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
