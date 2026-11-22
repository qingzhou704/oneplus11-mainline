#!/usr/bin/env python3
"""Offline unit tests for salami-tray top-bar label, icon, and menu model logic."""
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1] / "rootfs/salami-device/usr/lib/salami/salami-tray"
spec = importlib.util.spec_from_loader("salami_tray", SourceFileLoader("salami_tray", str(SOURCE)))
tray = importlib.util.module_from_spec(spec)
sys.modules["salami_tray"] = tray
spec.loader.exec_module(tray)


class SalamiTrayModelTests(unittest.TestCase):
    def _sample_status(self, *, mode="balanced", watts=0.0, bat_state="Charging", cap=82, cpu_t=32.4):
        return {
            "battery": {
                "capacity_pct": cap,
                "status": bat_state,
                "power_w": watts,
                "temp_c": 25.2,
                "start_threshold_pct": 75,
                "end_threshold_pct": 80,
            },
            "perf": {"mode": mode},
            "thermals_c": {"cpu_max": cpu_t, "gpu_max": 29.5, "skin": 24.8},
            "memory": {"ram_used_gib": 5.4, "ram_total_gib": 14.6, "zram": {"compr_mib": 12}},
            "storage": {"ufs_scheduler": "none", "read_ahead_kb": 256},
            "network": {"tcp_congestion_control": "bbr", "default_qdisc": "fq"},
        }

    def test_indicator_label_and_icon_for_charging_and_perf_modes(self):
        st_idle = self._sample_status(mode="balanced", watts=0.0)
        self.assertEqual(tray.format_indicator_label(st_idle), " 82% · 32°C")
        self.assertEqual(tray.choose_indicator_icon(st_idle), "phone-symbolic")

        st_vooc = self._sample_status(mode="balanced", watts=38.4, cpu_t=39.1)
        self.assertEqual(tray.format_indicator_label(st_vooc), " ⚡38W · 39°C")
        self.assertEqual(tray.choose_indicator_icon(st_vooc), "battery-good-charging-symbolic")

        st_eco = self._sample_status(mode="eco", watts=0.0, cpu_t=28.0)
        self.assertEqual(tray.format_indicator_label(st_eco), " 🌿 82% · 28°C")
        self.assertEqual(tray.choose_indicator_icon(st_eco), "power-profile-power-saver-symbolic")

        st_perf = self._sample_status(mode="performance", watts=0.0, cpu_t=41.0)
        self.assertEqual(tray.format_indicator_label(st_perf), " 🚀 82% · 41°C")
        self.assertEqual(tray.choose_indicator_icon(st_perf), "power-profile-performance-symbolic")

    def test_nearest_preset_and_summary_lines(self):
        self.assertEqual(tray.nearest_preset(31, tray.BRIGHTNESS_PRESETS), 35)
        self.assertEqual(tray.nearest_preset(98, tray.BRIGHTNESS_PRESETS), 100)
        self.assertEqual(tray.nearest_preset(55, tray.TORCH_PRESETS[1:]), 64)

        net = {"connectivity": "full", "services": {"ssh": "active", "nginx": "active"}}
        l_bat, l_temp, l_mem, l_net = tray.format_summary_lines(self._sample_status(), net)
        self.assertIn("75–80% 限充", l_bat)
        self.assertIn("CPU 32.4 °C", l_temp)
        self.assertIn("UFS [none/256K]", l_mem)
        self.assertIn("服务 2/2 正常", l_net)


if __name__ == "__main__":
    unittest.main(verbosity=2)
