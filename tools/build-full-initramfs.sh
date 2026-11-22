#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Build the complete persistent/maintenance ARM64 initramfs (firstboot.cpio)
# on a native ARM64 Ubuntu runner.
# usage: build-full-initramfs.sh KERNEL_TREE OUTPUT_DIR [BUILD_ID]
set -eu
k=$(realpath "${1:?kernel source tree}")
out=$(realpath -m "${2:?output directory}")
build_id=${3:-salami-ci}
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

[ "$(uname -m)" = aarch64 ] || { echo "run on native aarch64 host (ubuntu-24.04-arm)" >&2; exit 2; }
busybox_bin=$(command -v busybox)
[ -n "$busybox_bin" ] || { echo "busybox-static is required" >&2; exit 2; }

mkdir -p "$out" "$out/extra/bin" "$out/extra/etc" "$out/extra/usr/bin" "$out/extra/usr/sbin" "$out/extra/usr/lib/aarch64-linux-gnu"
gcc -O2 "$k/usr/gen_init_cpio.c" -o "$out/gen_init_cpio"
gcc -nostdlib -static "$here/tools/reboot-bootloader.S" -o "$out/extra/bin/reboot-bootloader"
strip "$out/extra/bin/reboot-bootloader"

printf 'linux_root\n' > "$out/extra/etc/root-partlabel"
printf 'salami maintenance image\n' > "$out/extra/etc/maintenance"
cp /etc/mke2fs.conf "$out/extra/etc/mke2fs.conf"

cp "$(command -v tar)" "$out/extra/usr/bin/tar"
for sbin_tool in dumpe2fs e2fsck mke2fs resize2fs sgdisk tune2fs; do
    cp "$(command -v "$sbin_tool")" "$out/extra/usr/sbin/$sbin_tool"
done
ln -snf e2fsck "$out/extra/usr/sbin/fsck.ext4"
ln -snf mke2fs "$out/extra/usr/sbin/mkfs.ext4"

# Copy shared libraries needed by tar, e2fsprogs, and sgdisk
for bin in "$out/extra/usr/bin/tar" "$out/extra/usr/sbin/"*; do
    [ -f "$bin" ] && [ ! -L "$bin" ] || continue
    ldd "$bin" | awk '/=> \// {print $3} /^\t\/lib/ {print $1}' | while read -r so; do
        [ -f "$so" ] || continue
        cp -L "$so" "$out/extra/usr/lib/aarch64-linux-gnu/$(basename "$so")"
    done
done
cp -L /lib/ld-linux-aarch64.so.1 "$out/extra/usr/lib/ld-linux-aarch64.so.1"
cp -L /lib/ld-linux-aarch64.so.1 "$out/extra/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1"
ln -snf usr/lib "$out/extra/lib"

sh "$here/tools/build-ramfs.sh" "$busybox_bin" "$out/gen_init_cpio" "$out" "$build_id" "$out/extra"
