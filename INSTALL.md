# 一加 11（PHB110 / salami）Linux 刷入指南

## 一、适用机型与前提条件

1. **适用机型**：一加 11 国行版（**PHB110，`oplusboot.prjname=22811`**），底包为 ColorOS 16，Bootloader 已解锁，活动槽为 `a`。其他地区型号（如 CPH2449 / CPH2451）未实机验证，请勿直接照搬分区参数。
2. **准备工作**：电脑安装好 `adb` 与 `fastboot`，手机电量建议 **≥ 60%**。
3. **分区说明**：本方案将原 `userdata` 拆分为最小占位 `userdata`（如 4 GiB）+ `linux_root`（建议 64–128 GiB）+ `linux_home`（剩余空间），会清空手机上的 Android 用户数据；所有原厂启动、`super`、基带与校准分区保持原样不动。

---

## 二、第 1 步：备份本机原厂分区与蓝牙地址（必做）

修改任何分区前，务必先将**本机唯一校准数据与启动分区**备份到电脑并核对 SHA-256：

1. **记录本机蓝牙 MAC 地址**（Android 下执行）：
   ```sh
   adb shell getprop persist.vendor.service.bdroid.bdaddr
   ```
   记下输出的 `XX:XX:XX:XX:XX:XX`，后续安装时传入以恢复本机蓝牙地址。

2. **备份关键原厂分区**：
   - 启动分区：`boot_a`、`boot_b`、`init_boot_a`、`init_boot_b`、`vendor_boot_a`、`vendor_boot_b`、`dtbo_a`、`dtbo_b`、`vbmeta_a`、`vbmeta_b`
   - 射频与校准分区（每台设备唯一，不可跨机混用）：`modemst1`、`modemst2`、`fsg`、`fsc`、`oplusstanvbk_a`、`oplusstanvbk_b`、`oplusdycnvbk`、`persist`
   - 全盘（`sda`–`sdf`）主备 GPT 分区表

---

## 三、第 2 步：获取镜像（下载预构建包或自行编译）

### 方式 A（推荐）：直接下载 Releases 预构建包
前往本仓库 **[Releases](https://github.com/qingzhou704/oneplus11-mainline-linux/releases)** 下载最新版本：
- `boot.img`
- `rootfs.tar.xz`
- `SHA256SUMS`（下载后执行 `sha256sum -c SHA256SUMS` 确认校验通过）

### 方式 B：从源码自行构建
在 Ubuntu 24.04+ 构建机（需安装 `mmdebstrap`、`qemu-user-static`、`aarch64-linux-gnu-gcc`、`m4`、`alsatplg`）上：

1. **构建内核与模块包**：
   按 `patches/` 顺序将补丁应用至 Linux 内核源码后执行：
   ```sh
   sh tools/build-kernel.sh /path/to/kernel /path/to/kernel-out /path/to/out/kernel-pkg /path/to/firstboot.cpio -salami068
   ```
2. **构建配套包与桌面根文件系统**：
   ```sh
   sudo env \
     AUDIOREACH_TOPOLOGY_DIR=/path/to/audioreach-topology \
     GIS_DEB=/path/to/gnome-initial-setup_+salami3_arm64.deb \
     QCOM_VA_DEB=/path/to/qcom-va-driver_1.1.1-1_arm64.deb \
     GRD_DEB=/path/to/gnome-remote-desktop_+salami3_arm64.deb \
     sh tools/build-desktop-rootfs.sh \
       /var/tmp/salami-desktop-release \
       /path/to/out/kernel-pkg/linux-image-7.3.5-salami068.deb \
       /path/to/rmtfs_1.1.1-2+salami1_arm64.deb
   ```

---

## 四、第 3 步：刷入系统

### 1. 内存临时启动进入维护环境
手机进入 Fastboot 后，先临时启动 `boot.img`（尚未建立 `linux_root` 时会自动进入 USB 维护环境 `192.168.77.2:2323`，不写任何分区）：
```sh
fastboot -s <SERIAL> boot boot.img
```
电脑 USB 网卡获取 `192.168.77.10` 后连接 `telnet 192.168.77.2 2323`，先执行防超时保持命令：
```sh
touch /run/keep
```

### 2. 划分 `linux_root` 与 `linux_home`
在维护环境中仅对原 `userdata` 末尾空间使用 `sgdisk` 缩减 `userdata` 并新建两个分区（切勿改动前面任何原厂分区）：
- `linux_root`：建议 `64 GiB`–`128 GiB`
- `linux_home`：剩余空间

### 3. 写入桌面根文件系统
维护环境运行在内存中（`/run` 为 tmpfs），可通过电脑起一个临时 HTTP 文件服务将 `rootfs.tar.xz` 与 `tools/install-clean-system.sh` 拉入手机：
```sh
# 电脑端：在存放 rootfs.tar.xz 与 install-clean-system.sh 的目录执行
python3 -m http.server 8000 --bind 192.168.77.10

# 手机维护壳（telnet 192.168.77.2 2323）内执行，将蓝牙地址替换为第 1 步备份的本机地址
wget http://192.168.77.10:8000/install-clean-system.sh -O /run/install-clean-system.sh
wget http://192.168.77.10:8000/rootfs.tar.xz -O /run/rootfs.tar.xz
sh /run/install-clean-system.sh /run/rootfs.tar.xz AA:BB:CC:DD:EE:FF
```

### 4. 刷入 `boot_a` 并重启进入 Ubuntu
回到 Fastboot 刷入匹配的 `boot.img`：
```sh
fastboot -s <SERIAL> flash boot_a boot.img
fastboot -s <SERIAL> reboot
```
重启后手机屏幕自动进入中文 GNOME 初始向导，创建账户后即可直接进入 Ubuntu 桌面。

如需后续开启 SSH 远程登录，在终端放入公钥后执行：
```sh
sudo systemctl unmask ssh.service ssh.socket
sudo systemctl enable --now ssh.service
```
