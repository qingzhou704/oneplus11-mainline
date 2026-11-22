#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Build rootfs/salami-device into OUT/salami-device.deb (copied to a Linux filesystem first so
# modes are exact). Needs aarch64-linux-gnu-gcc.   usage: build-device-deb.sh OUT
set -eu
out=${1:?output directory}
here=$(cd "$(dirname "$0")/.." && pwd)
pkg=$out/salami-device
rm -rf "$pkg"; mkdir -p "$out"
cp -r "$here/rootfs/salami-device" "$pkg"
# Python bytecode left by a local run of wifi-board is git-ignored, so without this the package
# contents depend on the build machine instead of the commit.
find "$pkg" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$pkg" -type f -name '*.pyc' -delete
find "$pkg" -type d -exec chmod 755 {} +
find "$pkg" -type f -exec chmod 644 {} +
chmod 755 "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/prerm" "$pkg/usr/lib/salami/usb-gadget" "$pkg/usr/lib/salami/mark-boot-successful" \
    "$pkg/usr/lib/salami/import-modem-data" "$pkg/usr/lib/salami/import-gpu-firmware" \
    "$pkg/usr/lib/salami/bluetooth-address" "$pkg/usr/lib/salami/wifi-board" \
    "$pkg/usr/lib/salami/power-key" "$pkg/usr/lib/salami/salami-ctl" \
    "$pkg/usr/lib/salami/salami-tray" "$pkg/usr/lib/salami/ufs-tune" \
    "$pkg/etc/NetworkManager/dispatcher.d/90-salami-wifi-powersave"
mkdir -p "$pkg/usr/bin"
ln -snf ../lib/salami/salami-ctl "$pkg/usr/bin/salami-ctl"
# Freestanding: the build host has an aarch64 compiler but no aarch64 libc headers.
aarch64-linux-gnu-gcc -O2 -ffreestanding -nostdlib -shared -fPIC -Wl,-z,noexecstack \
    -o "$pkg/usr/lib/salami/libllvm-host-cpu.so" "$here/rootfs/llvm-host-cpu.c"
chmod 644 "$pkg/usr/lib/salami/libllvm-host-cpu.so"
# AudioReach topology: set AUDIOREACH_TOPOLOGY_DIR to a checkout of
# https://github.com/Audioreach/audioreach-topology (needs m4, alsatplg).
tplg_src=${AUDIOREACH_TOPOLOGY_DIR:-$here/../../sources/audioreach-topology}
[ -d "$tplg_src" ] || { echo "missing audioreach-topology directory: set AUDIOREACH_TOPOLOGY_DIR ($tplg_src)" >&2; exit 2; }
tplg=$pkg/usr/lib/firmware/qcom/sm8550/salamisnd-tplg.bin
mkdir -p "$(dirname "$tplg")"
m4 -I "$here/audio" -I "$tplg_src" "$here/audio/salamisnd.m4" > "$out/salamisnd.conf"
alsatplg -c "$out/salamisnd.conf" -o "$tplg"
chmod 644 "$tplg"
dpkg-deb --root-owner-group -Zxz --build "$pkg" "$out/salami-device.deb" >/dev/null
sha256sum "$out/salami-device.deb"
