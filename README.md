# Ubuntu / Mainline Linux for OnePlus 11

[![CI](https://github.com/qingzhou704/oneplus11-mainline-linux/actions/workflows/ci.yml/badge.svg)](https://github.com/qingzhou704/oneplus11-mainline-linux/actions/workflows/ci.yml)
[![Build & Release](https://github.com/qingzhou704/oneplus11-mainline-linux/actions/workflows/release.yml/badge.svg)](https://github.com/qingzhou704/oneplus11-mainline-linux/actions/workflows/release.yml)

在一加 11（`PHB110 / salami / 骁龙 8 Gen 2 SM8550`）上运行原生 **Ubuntu Desktop 26.04**，采用 GNOME 桌面与主线 **Linux 7.3.5** 内核。

预构建刷机镜像发布在本仓库 **[Releases](https://github.com/qingzhou704/oneplus11-mainline-linux/releases)**，刷入步骤见 **[安装说明](INSTALL.md)**。

---

## 硬件支持

✅ 可用 · 🟡 部分支持 · ❌ 尚不支持

### 平台、显示与输入

| 功能 | 器件 / 实现 | 状态 | 说明 |
|---|---|---|---|
| 启动与存储 | SM8550 / UFS 4.0 | ✅ | 支持从内置 UFS 启动与多队列直通读写（`scheduler=none`），支持周期 `fstrim`。 |
| 内置显示 | 三星 AMB670YF07 + Iris7 旁路 | ✅ | `1440 × 3216` 原生分辨率，支持 `60 / 90 / 120 Hz` 运行时切帧、2048 级背光与户外阳光屏超亮激发（HBM）。 |
| 触控 | Synaptics S3908 I2C | ✅ | 支持多点触控、`60 / 90 / 120 Hz` 采样率同步、息屏双击亮屏（DT2W）、息屏断触省电与手套高灵敏模式。 |
| GPU 与桌面 | Adreno 740 / Freedreno / Turnip | ✅ | GNOME Wayland 桌面、OpenGL 与 Vulkan 硬件加速渲染。 |
| 实体按键 | PMIC / GPIO input | ✅ | 电源键短按亮息屏、长按弹出关机框；音量加/减键正常可用。 |
| 三段式静音键 | 双霍尔传感器 `ist8801` | ❌ | 暂无主线驱动。 |

### 无线、连接与外设

| 功能 | 器件 / 实现 | 状态 | 说明 |
|---|---|---|---|
| Wi-Fi | WCN7850 / `ath12k` | ✅ | 支持联网、开机自动连接与低延迟模式（默认关闭无线省电休眠）。 |
| 5G / LTE 移动数据 | 骁龙 X70 / QRTR / ModemManager | ✅ | 支持蜂窝移动数据、Wi-Fi 断外网自动切换至 5G（默认使用国内 HTTP 204 探针，海外用户可在 `/etc/NetworkManager/conf.d/` 覆盖 `[connectivity] uri=`），以及掉网自动重连自愈。 |
| 蓝牙 | WCN7850 / BlueZ / PipeWire | ✅ | 支持蓝牙键鼠、手柄及蓝牙音频连接。 |
| USB-C 接口 | DWC3 双角色 / UCSI | ✅ | 支持 USB NCM 有线网络，以及通过 OTG/扩展坞连接 U 盘、外置硬盘（exFAT / NTFS3）、键鼠、USB 声卡与有线网卡（含 2.5G/5G）。 |

### 音视频、电源与传感器

| 功能 | 器件 / 实现 | 状态 | 说明 |
|---|---|---|---|
| 视频硬件编解码 | Qualcomm Iris3 / VA-API | ✅ | 支持 H.264、HEVC、VP9、AV1 硬件解码与 H.264、HEVC 硬件编码；GNOME 远程桌面支持 VA-API 硬件编码。 |
| 扬声器与麦克风 | 双 TFA9873 + WCD9385 / AudioReach | 🟡 | 双扬声器外放与双麦克风录音可用；缺少原厂 DSP 扬声器振幅保护，建议避免长时间满音量播放。 |
| 电池与快充 | `qcom_battmgr` / SUPERVOOC | ✅ | 支持电量、电压、电流与实时功率读取；默认 80% 护航限充（可临时切 100% 定时恢复）；原装充电器支持最高约 50W+ SUPERVOOC 闪充，可随时切回 10W 低温慢充。 |
| 调频与温控 | CPUFreq / Devfreq / 14 路温区 | ✅ | 支持节能、均衡、满血性能（解锁 Cortex-X3 **3.19 GHz** 硬件睿频 + GPU 提频）三档联动及温控降频。 |
| 闪光灯与马达 | SPMI Flash LED / Haptics | ✅ | 支持后置手电筒多档调光与 X 轴线性马达震动反馈。 |
| 摄像头 / 屏下指纹 | Camera ISP / 光学指纹 | ❌ | 暂无主线驱动。 |

---

## 日常使用与控制

桌面右上角状态栏自带 **「一加 11 控制台」**（实时显示电量/充电功率与温度），点开即可直接切换，无需输命令：

- **性能档位**：节能静音 / 日常均衡 / 满血性能（3.19 GHz 睿频）
- **电池与快充**：80% 日常护航限充、6h/12h 临时充满 100% 自动恢复（实时显示倒计时）、SUPERVOOC 50W 全速闪充 / 温和限流快充 / 10W 低温慢充切换
- **屏幕与触控**：物理屏幕开关（远程连接时可单独熄灭手机屏）、亮度、阳光屏 HBM、`60 / 90 / 120 Hz` 刷新率、息屏双击亮屏 / 断触策略、手套模式、手电筒
- **远程与网络**：远程桌面硬编画质档位、一键系统体检（Doctor）、5G 基带状态与一键重连自愈、UFS `fstrim`、系统安全状态巡检

终端或 SSH 下也可使用 `salami-ctl`（自带 Bash 自动补全）：

```sh
salami-ctl                    # 查看电池/快充/性能/温度/显示/存储/网络总览
salami-ctl watch              # 实时刷新终端遥测看板（追踪峰值功率、温度与实时频率）
salami-ctl doctor             # 一键全栈健康体检（8 大维度 PASS/WARN/FAIL + 修复建议）
salami-ctl perf performance   # 切换 eco | balanced | performance
salami-ctl charge 100 --hours 6
salami-ctl vooc toggle        # 切换 50W 闪充 / 10W 慢充（支持 --cool 8 温和限流）
salami-ctl refresh 90         # 实时切换 60 | 90 | 120 Hz 刷新率（加 --no-persist 免提权临时切换）
salami-ctl hbm toggle         # 开关户外阳光屏高亮度激发
salami-ctl touch off-policy gesture  # gesture 双击亮屏 | sleep 息屏断触 | active
salami-ctl touch glove toggle # 开关手套触控模式
salami-ctl modem recover      # 一键重连自愈 5G 基带
```

---

## 安装与构建

- **直接刷入预构建镜像 / 分区与备份要求**：见 **[INSTALL.md](INSTALL.md)** 及 **[Releases](https://github.com/qingzhou704/oneplus11-mainline-linux/releases)**
- **从源码构建**：
  - `kernel/`：一加 11 主线设备树与内核配置片段
  - `patches/`：基于 Linux 7.3.5 与 Ubuntu 上游包的补丁集
  - `rootfs/`：设备集成包 `salami-device` 与桌面包清单
  - `tools/`：内核、设备包与桌面根文件系统构建及安装脚本（`build-kernel.sh`、`build-desktop-rootfs.sh`、`install-clean-system.sh`）

---

## 致谢与许可证

本项目基于 Linux 内核、Ubuntu、GNOME、Freedreno/Mesa 以及 Linux Qualcomm（`linux-msm`）社区的成果构建。

特别感谢以下上游项目与开发者：
- **[yzddmr6/onepluspad-2pro-mainline](https://github.com/yzddmr6/onepluspad-2pro-mainline)** 与 **[yzddmr6/android-mainline-port](https://github.com/yzddmr6/android-mainline-port)**：提供了主线移植工程方法论、RAM 安全试启动闭环、构建校验体系与大量高通平台实践参考。
- **Linux SM8550 / OnePlus 主线移植社区**：包括 OnePlus 12R（`aston`）主线适配参考、Vsevolod Nevorotov 的 Synaptics S3908 TouchComm 驱动工作，以及 [OnePlusOSS](https://github.com/OnePlusOSS) 开源参考代码。
- **[linux-msm/audioreach-topology](https://github.com/linux-msm/audioreach-topology)**、**[linux-msm/rmtfs](https://github.com/linux-msm/rmtfs)** 与 **[radxa-pkg/qcom-va-driver](https://github.com/radxa-pkg/qcom-va-driver)**：分别提供了音频拓扑、调制解调器远程文件系统服务与高通 Iris VA-API 视频编解码后端。

除文件另有声明外，本仓库原创集成代码与脚本采用 **GPL-2.0-only** 许可证。Linux 内核及各第三方组件保留各自原作者署名与许可证，详见 **[LICENSE](LICENSE)** 与 **[NOTICE](NOTICE)**。
