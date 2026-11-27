#!/usr/bin/env python3
"""Offline unit tests for salami-ctl hardware telemetry and safe sysfs controls."""
from importlib.machinery import SourceFileLoader
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1] / "rootfs/salami-device/usr/lib/salami/salami-ctl"
spec = importlib.util.spec_from_loader("salami_ctl", SourceFileLoader("salami_ctl", str(SOURCE)))
salami_ctl = importlib.util.module_from_spec(spec)
sys.modules["salami_ctl"] = salami_ctl
spec.loader.exec_module(salami_ctl)


class SalamiCtlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        r = Path(self.tmp.name)
        self.paths = salami_ctl.SysfsPaths(
            bat_dir=r / "bat",
            usb_dir=r / "usb",
            vooc_param=r / "vooc",
            vooc_cool_param=r / "vooc_cool",
            vooc_modprobe_conf=r / "modprobe.d" / "salami-vooc.conf",
            thermal_dir=r / "thermal",
            cpufreq_dir=r / "cpufreq",
            cpufreq_boost=r / "cpufreq" / "boost",
            gpu_devfreq_dir=r / "gpu_devfreq",
            ufs_queue_dir=r / "ufs_queue",
            torch_dir=r / "torch",
            backlight_dir=r / "backlight",
            drm_dir=r / "drm",
            panel_refresh_param=r / "refresh",
            panel_hbm_param=r / "panel_hbm",
            touch_refresh_param=r / "touch_refresh",
            touch_glove_param=r / "touch_glove",
            touch_power_mode_param=r / "touch_power_mode",
            touch_off_policy_file=r / "salami" / "touch-screen-off-mode",
            refresh_modprobe_conf=r / "modprobe.d" / "salami-refresh.conf",
            zram_mm_stat=r / "zram_mm_stat",
            proc_meminfo=r / "meminfo",
            proc_tcp_cc=r / "tcp_cc",
            proc_qdisc=r / "qdisc",
            sys_input=r / "sys_input",
            dev_input=r / "dev_input",
            grd_env_file=r / "env.d" / "60-salami-grd.conf",
            power_key_script=r / "fake_power_key.py",
            services_conf=r / "salami" / "services.conf",
            modem_guard_state=r / "run" / "modem-guard.json",
            proc_sys_dir=r / "proc_sys",
            cpu_vuln_dir=r / "cpu_vulns",
        )
        for d in (
            self.paths.bat_dir,
            self.paths.usb_dir,
            self.paths.thermal_dir / "thermal_zone0",
            self.paths.thermal_dir / "thermal_zone1",
            self.paths.thermal_dir / "thermal_zone2",
            self.paths.cpufreq_dir / "policy0",
            self.paths.cpufreq_dir / "policy3",
            self.paths.cpufreq_dir / "policy7",
            self.paths.gpu_devfreq_dir,
            self.paths.ufs_queue_dir,
            self.paths.torch_dir,
            self.paths.backlight_dir,
            self.paths.drm_dir / "card1-DSI-1",
            self.paths.sys_input / "event3" / "device",
            self.paths.dev_input,
            self.paths.touch_off_policy_file.parent,
        ):
            d.mkdir(parents=True, exist_ok=True)

        self._write(self.paths.bat_dir / "capacity", "78")
        self._write(self.paths.bat_dir / "status", "Charging")
        self._write(self.paths.bat_dir / "voltage_now", "8400000")
        self._write(self.paths.bat_dir / "current_now", "4500000")
        self._write(self.paths.bat_dir / "power_now", "37800000")
        self._write(self.paths.bat_dir / "temp", "345")
        self._write(self.paths.bat_dir / "charge_control_start_threshold", "75")
        self._write(self.paths.bat_dir / "charge_control_end_threshold", "80")
        self._write(self.paths.bat_dir / "cycle_count", "5")
        self._write(self.paths.bat_dir / "state_of_health", "100")
        self._write(self.paths.usb_dir / "online", "1")
        self._write(self.paths.usb_dir / "voltage_now", "8900000")
        self._write(self.paths.usb_dir / "current_now", "4300000")
        self._write(self.paths.vooc_param, "Y")
        self._write(self.paths.vooc_cool_param, "0")
        self._write(self.paths.touch_glove_param, "N")
        self._write(self.paths.touch_power_mode_param, "active")
        self._write(self.paths.touch_off_policy_file, "gesture")
        self._write(self.paths.thermal_dir / "thermal_zone0" / "type", "cpu7-top-thermal")
        self._write(self.paths.thermal_dir / "thermal_zone0" / "temp", "36500")
        self._write(self.paths.thermal_dir / "thermal_zone1" / "type", "gpuss-0-thermal")
        self._write(self.paths.thermal_dir / "thermal_zone1" / "temp", "31200")
        self._write(self.paths.thermal_dir / "thermal_zone2" / "type", "skin-msm-thermal")
        self._write(self.paths.thermal_dir / "thermal_zone2" / "temp", "29400")
        for pol, hw in (("policy0", "2016000"), ("policy3", "2803200"), ("policy7", "2956800")):
            self._write(self.paths.cpufreq_dir / pol / "scaling_governor", "schedutil")
            self._write(self.paths.cpufreq_dir / pol / "scaling_max_freq", hw)
            self._write(self.paths.cpufreq_dir / pol / "cpuinfo_max_freq", hw)
        self._write(self.paths.cpufreq_boost, "0")
        self._write(self.paths.cpufreq_dir / "policy7" / "scaling_boost_frequencies", "3187200")
        self._write(self.paths.gpu_devfreq_dir / "min_freq", "220000000")
        self._write(self.paths.gpu_devfreq_dir / "max_freq", "680000000")
        self._write(self.paths.ufs_queue_dir / "scheduler", "[none] mq-deadline kyber bfq")
        self._write(self.paths.ufs_queue_dir / "read_ahead_kb", "256")
        self._write(self.paths.torch_dir / "brightness", "0")
        self._write(self.paths.torch_dir / "max_brightness", "255")
        self._write(self.paths.backlight_dir / "brightness", "628")
        self._write(self.paths.backlight_dir / "max_brightness", "2047")
        self._write(self.paths.drm_dir / "card1-DSI-1" / "dpms", "On")
        self._write(self.paths.panel_refresh_param, "120")
        self._write(self.paths.panel_hbm_param, "N")
        self._write(self.paths.touch_refresh_param, "120")
        self._write(self.paths.zram_mm_stat, "104857600 34952533 40000000 0 40000000 0 0 0 0")
        self._write(self.paths.proc_meminfo, "MemTotal:       15000000 kB\nMemAvailable:   10000000 kB\n")
        self._write(self.paths.proc_tcp_cc, "bbr")
        self._write(self.paths.proc_qdisc, "fq")
        self._write(self.paths.sys_input / "event3" / "device" / "name", "qcom-spmi-haptics")
        (self.paths.dev_input / "event3").write_bytes(b"")

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.write_text(text + "\n", encoding="utf-8")

    def test_status_json_and_formatted_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = salami_ctl.main(["status", "--json"], self.paths)
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["battery"]["capacity_pct"], 78)
        self.assertEqual(data["battery"]["power_w"], 37.8)
        self.assertTrue(data["battery"]["vooc_enabled"])
        self.assertEqual(data["thermals_c"]["cpu_max"], 36.5)
        self.assertEqual(data["thermals_c"]["gpu_max"], 31.2)
        self.assertEqual(data["thermals_c"]["skin"], 29.4)
        self.assertEqual(data["network"]["tcp_congestion_control"], "bbr")
        self.assertEqual(data["network"]["default_qdisc"], "fq")
        self.assertEqual(data["memory"]["zram"]["ratio"], 3.0)

        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            self.assertEqual(salami_ctl.main(["status"], self.paths), 0)
        self.assertIn("37.80 W", buf2.getvalue())
        self.assertIn("bbr + fq", buf2.getvalue())

    def test_charge_threshold_write_order_prevents_kernel_einval(self):
        # Track every write sequence so start_threshold is NEVER > end_threshold
        events: list[tuple[str, int]] = []
        start_p = self.paths.bat_dir / "charge_control_start_threshold"
        end_p = self.paths.bat_dir / "charge_control_end_threshold"

        orig_write_text = Path.write_text

        def checked_write(p: Path, data: str, *args, **kwargs):
            orig_write_text(p, data, *args, **kwargs)
            if p in (start_p, end_p):
                s = int(start_p.read_text())
                e = int(end_p.read_text())
                events.append((p.name, int(data.strip())))
                self.assertLessEqual(s, e, f"Invalid transient state start={s} > end={e}")

        with mock.patch.object(Path, "write_text", checked_write):
            # 75/80 -> 95/100 must write end(100) BEFORE start(95)
            self.assertEqual(salami_ctl.set_charge_limit(100, self.paths), (95, 100))
            self.assertEqual(events, [
                ("charge_control_end_threshold", 100),
                ("charge_control_start_threshold", 95),
            ])
            events.clear()
            # 95/100 -> 75/80 must write start(75) BEFORE end(80)
            self.assertEqual(salami_ctl.set_charge_limit(80, self.paths), (75, 80))
            self.assertEqual(events, [
                ("charge_control_start_threshold", 75),
                ("charge_control_end_threshold", 80),
            ])

        with self.assertRaises(ValueError):
            salami_ctl.set_charge_limit(30, self.paths)
        with self.assertRaises(ValueError):
            salami_ctl.set_charge_limit(105, self.paths)

    def test_torch_on_off_toggle_and_clamp(self):
        self.assertEqual(salami_ctl.set_torch("toggle", None, self.paths), 64)
        self.assertEqual(salami_ctl.set_torch("status", None, self.paths), 64)
        self.assertEqual(salami_ctl.set_torch("toggle", None, self.paths), 0)
        self.assertEqual(salami_ctl.set_torch("on", 500, self.paths), 255)
        self.assertEqual(salami_ctl.set_torch("off", None, self.paths), 0)

    def test_brightness_percent_relative_and_safe_floor(self):
        raw, pct = salami_ctl.set_brightness("50%", self.paths)
        self.assertEqual(pct, 50)
        self.assertEqual(raw, 1024)
        raw, pct = salami_ctl.set_brightness("+20", self.paths)
        self.assertEqual(pct, 70)
        raw, pct = salami_ctl.set_brightness("-99", self.paths)
        self.assertEqual(pct, 1)
        self.assertGreaterEqual(raw, 20)

    def test_find_haptics_device(self):
        dev = salami_ctl.find_haptics_device(self.paths)
        self.assertEqual(dev, self.paths.dev_input / "event3")

    def test_perf_modes_switch_governors_and_sm8550_opps(self):
        self.assertEqual(salami_ctl.detect_perf_profile(self.paths)["mode"], "balanced")

        gpu_min_p = self.paths.gpu_devfreq_dir / "min_freq"
        gpu_max_p = self.paths.gpu_devfreq_dir / "max_freq"
        orig_write = Path.write_text

        def checked_gpu_write(p: Path, data: str, *args, **kwargs):
            orig_write(p, data, *args, **kwargs)
            if p in (gpu_min_p, gpu_max_p):
                self.assertLessEqual(int(gpu_min_p.read_text()), int(gpu_max_p.read_text()))

        with mock.patch.object(Path, "write_text", checked_gpu_write):
            eco = salami_ctl.set_perf_profile("eco", self.paths)
            self.assertEqual(eco["mode"], "eco")
            self.assertEqual(eco["clusters"]["policy0"]["max_mhz"], 1555)
            self.assertEqual(eco["clusters"]["policy3"]["max_mhz"], 1786)
            self.assertEqual(eco["clusters"]["policy7"]["max_mhz"], 1843)
            self.assertEqual(eco["gpu"], {"min_mhz": 220, "max_mhz": 401})

            perf = salami_ctl.set_perf_profile("performance", self.paths)
            self.assertEqual(perf["mode"], "performance")
            self.assertTrue(perf["boost"])
            self.assertEqual(perf["clusters"]["policy7"]["governor"], "performance")
            self.assertEqual(perf["clusters"]["policy7"]["max_mhz"], 3187)
            self.assertEqual(perf["gpu"], {"min_mhz": 401, "max_mhz": 680})

            bal = salami_ctl.set_perf_profile("balanced", self.paths)
            self.assertEqual(bal["mode"], "balanced")
            self.assertFalse(bal["boost"])
            self.assertEqual(bal["clusters"]["policy7"]["governor"], "schedutil")
            self.assertEqual(bal["gpu"], {"min_mhz": 220, "max_mhz": 680})

        with self.assertRaises(ValueError):
            salami_ctl.set_perf_profile("turbo", self.paths)

    def test_refresh_rate_atomic_sync_and_validation(self):
        st = salami_ctl.set_refresh_rate(90, self.paths)
        self.assertEqual(st["configured_hz"], 90)
        self.assertTrue(st["runtime_panel_applied"])
        self.assertTrue(st["runtime_touch_applied"])
        self.assertEqual(st["active_panel_hz"], 90)
        self.assertEqual(st["active_touch_hz"], 90)
        conf = self.paths.refresh_modprobe_conf.read_text(encoding="utf-8")
        self.assertIn("options panel_samsung_amb670yf07_iris7 refresh=90\n", conf)
        self.assertIn("options synaptics_tcm_i2c refresh=90\n", conf)
        with self.assertRaises(ValueError):
            salami_ctl.set_refresh_rate(144, self.paths)

    def test_sunlight_hbm_toggle(self):
        self.assertEqual(salami_ctl.get_hbm_state(self.paths), (True, False))
        self.assertTrue(salami_ctl.set_hbm_state("toggle", self.paths))
        self.assertEqual(self.paths.panel_hbm_param.read_text().strip(), "1")
        self.assertFalse(salami_ctl.set_hbm_state("off", self.paths))
        self.assertEqual(self.paths.panel_hbm_param.read_text().strip(), "0")

    def test_remote_physical_screen_control(self):
        dpms_file = self.paths.drm_dir / "card1-DSI-1" / "dpms"
        self.paths.power_key_script.write_text(
            "from pathlib import Path\n"
            f"DPMS = Path({str(dpms_file)!r})\n"
            "class UInputWakeDevice:\n"
            "    def open(self): pass\n"
            "    def close(self): pass\n"
            "class Seat0GnomeBackend:\n"
            "    def __init__(self, wake_emitter=None): pass\n"
            "    def is_screen_off(self): return DPMS.read_text().strip() != 'On'\n"
            "    def wake_screen(self): DPMS.write_text('On\\n')\n"
            "    def blank_screen(self): DPMS.write_text('Off\\n')\n",
            encoding="utf-8",
        )
        self.assertEqual(salami_ctl.control_physical_screen("status", self.paths), "On")
        self.assertEqual(salami_ctl.control_physical_screen("off", self.paths), "Off")
        self.assertEqual(salami_ctl.control_physical_screen("toggle", self.paths), "On")
        self.assertEqual(salami_ctl.control_physical_screen("toggle", self.paths), "Off")

    def test_custom_services_conf_parsing_and_validation(self):
        self.paths.services_conf.parent.mkdir(parents=True, exist_ok=True)
        self.paths.services_conf.write_text(
            "# custom operator units\n"
            "myapp.service | My Web App | restart\n"
            "bad;rm.service | Evil | restart\n"
            "other.service | InvalidVerb | stop\n",
            encoding="utf-8",
        )
        with mock.patch.object(salami_ctl, "_run_cmd", return_value="disabled"):
            entries = salami_ctl.discover_managed_services(self.paths)
        self.assertEqual(entries, [("myapp.service", "My Web App", "restart")])

        # Verify service stop, start, default restart, and invalid action rejection
        with (
            mock.patch.object(salami_ctl, "_run_cmd", return_value="disabled"),
            mock.patch.object(salami_ctl.subprocess, "run") as m_run,
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(salami_ctl.main(["service", "myapp.service", "stop"], self.paths), 0)
            m_run.assert_called_with(["/usr/bin/systemctl", "stop", "myapp.service"], check=True)
            self.assertIn("已完", buf.getvalue().replace("已完成", "已完"))
            self.assertIn("停止", buf.getvalue())

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                self.assertEqual(salami_ctl.main(["service", "myapp", "start"], self.paths), 0)
            m_run.assert_called_with(["/usr/bin/systemctl", "start", "myapp.service"], check=True)
            self.assertIn("启动", buf2.getvalue())

            self.assertEqual(salami_ctl.main(["service", "myapp.service", "kill"], self.paths), 1)

    def test_rdp_qp_presets_and_bounds(self):
        self.assertEqual(salami_ctl.get_rdp_qp(self.paths), 22)
        qp, _ = salami_ctl.set_rdp_qp("fast", self.paths)
        self.assertEqual(qp, 27)
        self.assertEqual(salami_ctl.get_rdp_qp(self.paths), 27)
        qp, _ = salami_ctl.set_rdp_qp("hq", self.paths)
        self.assertEqual(qp, 18)
        qp, _ = salami_ctl.set_rdp_qp("31", self.paths)
        self.assertEqual(qp, 31)
        with self.assertRaises(ValueError):
            salami_ctl.set_rdp_qp("0", self.paths)
        with self.assertRaises(ValueError):
            salami_ctl.set_rdp_qp("55", self.paths)

    def test_vooc_runtime_toggle_cool_down_and_persist(self):
        st = salami_ctl.set_vooc_state("off", cool_down=4, persist=True, paths=self.paths)
        self.assertFalse(st["enabled"])
        self.assertEqual(st["cool_down"], 4)
        self.assertEqual(st["configured"], False)
        self.assertIn("vooc=0", self.paths.vooc_modprobe_conf.read_text(encoding="utf-8"))

        st2 = salami_ctl.set_vooc_state("toggle", cool_down=0, persist=True, paths=self.paths)
        self.assertTrue(st2["enabled"])
        self.assertEqual(st2["cool_down"], 0)
        self.assertEqual(st2["configured"], True)
        self.assertNotIn("vooc_cool_down=", self.paths.vooc_modprobe_conf.read_text(encoding="utf-8"))

        # Persisting cool_down writes both vooc and vooc_cool_down, including action='status'
        st3 = salami_ctl.set_vooc_state("status", cool_down=8, persist=True, paths=self.paths)
        self.assertTrue(st3["enabled"])
        self.assertEqual(st3["cool_down"], 8)
        conf3 = self.paths.vooc_modprobe_conf.read_text(encoding="utf-8")
        self.assertIn("options qcom_battmgr vooc=1 vooc_cool_down=8\n", conf3)

    def test_touch_glove_power_mode_and_screen_off_policy(self):
        self.assertFalse(salami_ctl.get_touch_status(self.paths)["glove_enabled"])
        self.assertTrue(salami_ctl.set_touch_glove("toggle", self.paths))
        self.assertEqual(self.paths.touch_glove_param.read_text().strip(), "1")
        self.assertEqual(salami_ctl.set_touch_power_mode("gesture", self.paths), "gesture")

        # When DSI is Off, changing off-policy immediately applies to touch_power_mode_param
        (self.paths.drm_dir / "card1-DSI-1" / "dpms").write_text("Off\n", encoding="utf-8")
        st = salami_ctl.set_touch_off_policy("sleep", self.paths)
        self.assertEqual(st["off_policy"], "sleep")
        self.assertEqual(self.paths.touch_power_mode_param.read_text().strip(), "sleep")

    def test_modem_guard_two_strike_recovery_and_backoff(self):
        recover_calls = []

        def fake_wedged():
            return {
                "present": True,
                "state": "searching",
                "power_state": "on",
                "sim_present": True,
                "ip": "",
            }

        def fake_recover():
            recover_calls.append(1)
            return {
                "present": True,
                "state": "connected",
                "power_state": "on",
                "sim_present": True,
                "ip": "10.86.1.2/32",
            }

        r1 = salami_ctl.guard_modem(self.paths, now=1000.0, status_fn=fake_wedged, recover_fn=fake_recover)
        self.assertEqual(r1["action"], "monitoring")
        self.assertEqual(len(recover_calls), 0)

        r2 = salami_ctl.guard_modem(self.paths, now=1120.0, status_fn=fake_wedged, recover_fn=fake_recover)
        self.assertEqual(r2["action"], "recovered")
        self.assertEqual(len(recover_calls), 1)
        self.assertEqual(r2["guard_state"]["consecutive_stuck"], 0)

    def test_security_status_audit(self):
        for rel, expected in salami_ctl.SECURITY_SYSCTL_EXPECT:
            p = self.paths.proc_sys_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"{expected}\n", encoding="utf-8")
        self.paths.cpu_vuln_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.cpu_vuln_dir / "spectre_v2").write_text("Mitigation: CSV2, BHB\n", encoding="utf-8")
        (self.paths.cpu_vuln_dir / "meltdown").write_text("Not affected\n", encoding="utf-8")

        sec = salami_ctl.collect_security_status(self.paths)
        self.assertEqual(sec["sysctl_ok"], len(salami_ctl.SECURITY_SYSCTL_EXPECT))
        self.assertEqual(sec["cpu_unmitigated"], [])
        self.assertIn("全部就绪", salami_ctl.format_security_status(sec))
        self.assertIn("0 项未防护", salami_ctl.format_security_status(sec))

        # Verify unmitigated CPU vulnerabilities are dynamically reported, never hardcoded as 0
        (self.paths.cpu_vuln_dir / "spectre_v2").write_text("Vulnerable: unmitigated\n", encoding="utf-8")
        sec_vuln = salami_ctl.collect_security_status(self.paths)
        self.assertEqual(sec_vuln["cpu_unmitigated"], ["spectre_v2"])
        formatted_vuln = salami_ctl.format_security_status(sec_vuln)
        self.assertIn("1 项未缓解: spectre_v2", formatted_vuln)
        self.assertNotIn("0 项未防护", formatted_vuln)

    def test_discharging_negative_power_and_duration_formatting(self):
        self._write(self.paths.bat_dir / "status", "Discharging")
        self._write(self.paths.bat_dir / "power_now", "-4250000")
        data = salami_ctl.collect_status(self.paths)
        self.assertEqual(data["battery"]["power_w"], 4.25)
        rendered = salami_ctl.format_status(data)
        self.assertIn("放电 4.25 W", rendered)

        self.assertEqual(salami_ctl.format_duration_short(0), "")
        self.assertEqual(salami_ctl.format_duration_short(42), "<1m")
        self.assertEqual(salami_ctl.format_duration_short(1800), "30m")
        self.assertEqual(salami_ctl.format_duration_short(3660), "1h01m")
        self.assertEqual(salami_ctl.format_duration_short(7200), "2h")

    def test_batched_systemd_unit_query_and_cur_mhz_telemetry(self):
        self._write(self.paths.cpufreq_dir / "policy7" / "scaling_cur_freq", "2419200")
        self._write(self.paths.gpu_devfreq_dir / "cur_freq", "491000000")
        perf = salami_ctl.detect_perf_profile(self.paths)
        self.assertEqual(perf["clusters"]["policy7"]["cur_mhz"], 2419)
        self.assertEqual(perf["gpu"]["cur_mhz"], 491)

        sample_show = (
            "Id=ssh.service\nUnitFileState=enabled\nActiveState=active\n\n"
            "Id=nginx.service\nUnitFileState=disabled\nActiveState=inactive\n"
        )
        with mock.patch.object(salami_ctl, "_run_cmd", return_value=sample_show) as mocked:
            entries = salami_ctl.discover_managed_services(self.paths)
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(entries, [("ssh.service", "SSH 远程服务", "restart")])

    def test_refresh_no_persist_only_updates_runtime_sysfs(self):
        st = salami_ctl.set_refresh_rate(90, self.paths, persist=False)
        self.assertTrue(st["runtime_panel_applied"])
        self.assertTrue(st["runtime_touch_applied"])
        self.assertFalse(st["persisted"])
        self.assertFalse(self.paths.refresh_modprobe_conf.exists())

        # Failing to apply runtime sysfs with --no-persist must fail closed, not exit 0
        self.paths.panel_refresh_param.unlink()
        self.paths.touch_refresh_param.unlink()
        with self.assertRaises(FileNotFoundError):
            salami_ctl.set_refresh_rate(60, self.paths, persist=False)

    def test_find_gsm_connection_and_disabled_optional_service_restart(self):
        sample_nm = "aaa-111:802-11-wireless\nbbb-222:gsm\n"
        with mock.patch.object(salami_ctl, "_run_cmd", return_value=sample_nm):
            self.assertEqual(salami_ctl.find_gsm_connection_name(), "bbb-222")
        with mock.patch.object(salami_ctl, "_run_cmd", return_value=""):
            self.assertEqual(salami_ctl.find_gsm_connection_name(), "mobile")

        sample_show = (
            "Id=docker.service\nUnitFileState=disabled\nActiveState=inactive\n\n"
            "Id=nginx.service\nUnitFileState=not-found\nActiveState=inactive\n"
        )
        with mock.patch.object(salami_ctl, "_run_cmd", return_value=sample_show):
            allowed = salami_ctl.allowed_service_units(self.paths)
        self.assertIn("docker.service", allowed)
        self.assertNotIn("nginx.service", allowed)

    def test_doctor_v4l2_by_name_all_ufs_luns_and_unreadable_sysctl(self):
        r = Path(self.tmp.name)
        self.paths.dri_dir = r / "dri"
        self.paths.dev_dir = r / "dev"
        self.paths.v4l2_sys_dir = r / "sys_v4l2"
        self.paths.ufs_host_dir = r / "ufshc"
        self.paths.va_driver_dir = r / "va"
        self.paths.regdb_file = r / "regulatory.db"
        self.paths.root_mount = r
        self.paths.home_mount = r
        for d in (
            self.paths.dri_dir,
            self.paths.dev_dir,
            self.paths.v4l2_sys_dir / "video0",
            self.paths.v4l2_sys_dir / "video2",
            self.paths.v4l2_sys_dir / "video3",
            self.paths.ufs_host_dir / "host0/target0:0:0/0:0:0:0/block/sda/queue",
            self.paths.ufs_host_dir / "host0/target0:0:0/0:0:0:3/block/sdd/queue",
            self.paths.va_driver_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        for f in (
            self.paths.dri_dir / "renderD128",
            self.paths.dev_dir / "video0",
            self.paths.dev_dir / "video2",
            self.paths.dev_dir / "video3",
            self.paths.va_driver_dir / "qcom_drv_video.so",
            self.paths.regdb_file,
        ):
            f.write_text("", encoding="utf-8")
        # UVC webcam occupies video0 while Iris3 is shifted to video2/video3
        self._write(self.paths.v4l2_sys_dir / "video0" / "name", "USB UVC Camera")
        self._write(self.paths.v4l2_sys_dir / "video2" / "name", "qcom-iris-decoder")
        self._write(self.paths.v4l2_sys_dir / "video3" / "name", "qcom-iris-encoder")
        self._write(self.paths.ufs_host_dir / "host0/target0:0:0/0:0:0:0/block/sda/queue/scheduler", "[none] mq-deadline")
        self._write(self.paths.ufs_host_dir / "host0/target0:0:0/0:0:0:3/block/sdd/queue/scheduler", "none [mq-deadline]")
        for rel, expected in salami_ctl.SECURITY_SYSCTL_EXPECT:
            p = self.paths.proc_sys_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"{expected}\n", encoding="utf-8")
        self.paths.cpu_vuln_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.cpu_vuln_dir / "meltdown").write_text("Not affected\n", encoding="utf-8")

        orig_access = salami_ctl.os.access

        def fake_access(path, mode):
            if str(path).endswith("net/core/bpf_jit_harden") and mode == salami_ctl.os.R_OK:
                return False
            return orig_access(path, mode)

        with mock.patch.object(salami_ctl.os, "access", side_effect=fake_access):
            rep = salami_ctl.collect_doctor_report(self.paths, live_override=False)
        by_id = {c["id"]: c for c in rep["checks"]}
        self.assertEqual(by_id["gpu_video"]["status"], "PASS")
        self.assertIn("/dev/video2", by_id["gpu_video"]["detail"])
        self.assertEqual(by_id["storage_memory"]["status"], "WARN")
        self.assertIn("sdd=mq-deadline", by_id["storage_memory"]["detail"])
        self.assertEqual(by_id["security"]["status"], "WARN")
        self.assertIn("net.core.bpf_jit_harden", by_id["security"]["detail"])

    def test_doctor_pass_warn_and_fail_diagnostics(self):
        r = Path(self.tmp.name)
        self.paths.dri_dir = r / "dri"
        self.paths.dev_dir = r / "dev"
        self.paths.v4l2_sys_dir = r / "no_v4l2"
        self.paths.ufs_host_dir = r / "no_ufshc"
        self.paths.va_driver_dir = r / "va"
        self.paths.regdb_file = r / "regulatory.db"
        self.paths.root_mount = r
        self.paths.home_mount = r
        for d in (self.paths.dri_dir, self.paths.dev_dir, self.paths.va_driver_dir):
            d.mkdir(parents=True, exist_ok=True)
        for f in (
            self.paths.dri_dir / "renderD128",
            self.paths.dev_dir / "video0",
            self.paths.dev_dir / "video1",
            self.paths.va_driver_dir / "qcom_drv_video.so",
            self.paths.regdb_file,
        ):
            f.write_text("", encoding="utf-8")
        for rel, expected in salami_ctl.SECURITY_SYSCTL_EXPECT:
            p = self.paths.proc_sys_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"{expected}\n", encoding="utf-8")
        self.paths.cpu_vuln_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.cpu_vuln_dir / "meltdown").write_text("Not affected\n", encoding="utf-8")

        report = salami_ctl.collect_doctor_report(self.paths, live_override=False)
        self.assertEqual(report["overall"], "PASS", salami_ctl.format_doctor_report(report))
        self.assertEqual(report["counts"]["fail"], 0)
        self.assertEqual(report["counts"]["warn"], 0)

        # Panel/touch refresh mismatch triggers WARN
        self._write(self.paths.touch_refresh_param, "60")
        warn_report = salami_ctl.collect_doctor_report(self.paths, live_override=False)
        self.assertEqual(warn_report["overall"], "WARN")
        self.assertIn("刷新率不一致", salami_ctl.format_doctor_report(warn_report))

        # Missing GPU render node triggers FAIL and CLI exit code 1
        (self.paths.dri_dir / "renderD128").unlink()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = salami_ctl.main(["doctor", "--json"], self.paths)
        self.assertEqual(rc, 1)
        fail_report = json.loads(buf.getvalue())
        self.assertEqual(fail_report["overall"], "FAIL")

    def test_watch_frame_tracks_peaks_and_respects_count(self):
        peaks: dict[str, float] = {}
        st1 = salami_ctl.collect_status(self.paths)
        frame1 = salami_ctl.render_watch_frame(st1, peaks, 1.0, 0.0)
        self.assertIn("峰值 37.80 W", frame1)
        self.assertIn("CPU 36.5°C", frame1)

        self._write(self.paths.bat_dir / "power_now", "12000000")
        st2 = salami_ctl.collect_status(self.paths)
        frame2 = salami_ctl.render_watch_frame(st2, peaks, 1.0, 2.0)
        self.assertIn("12.00 W (峰值 37.80 W)", frame2)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = salami_ctl.main(["watch", "-n", "0.5", "--count", "1"], self.paths)
        self.assertEqual(rc, 0)
        self.assertIn("实时遥测看板", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
