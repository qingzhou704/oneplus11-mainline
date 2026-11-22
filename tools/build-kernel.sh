#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Build the OnePlus 11 (salami) kernel Image + appended DTB + modules + AVB boot.img + .deb.
# usage: build-kernel.sh KERNEL_TREE BUILD_DIR OUTPUT_DIR INITRAMFS_CPIO [LOCALVERSION_TAG]
set -eu
k=$(realpath "${1:?kernel source tree}")
b=$(realpath -m "${2:?kernel build directory}")
o=$(realpath -m "${3:?package output directory}")
cpio=$(realpath -e "${4:?initramfs cpio archive}")
localver=${5:--salami068}
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

cp "$here/kernel/sm8550-oneplus-salami.dts" "$here/kernel"/sm8550-oneplus-salami*.dtsi \
    "$k/arch/arm64/boot/dts/qcom/"

mkdir -p "$b"
cc_prefix=${CROSS_COMPILE:-aarch64-linux-gnu-}
if [ ! -f "$b/.config" ]; then
    make -C "$k" O="$b" ARCH=arm64 CROSS_COMPILE="$cc_prefix" \
        defconfig qcom.config
fi
KCONFIG_CONFIG="$b/.config" "$k/scripts/kconfig/merge_config.sh" -m -O "$b" \
    "$b/.config" "$here/kernel/kernel.config"
"$k/scripts/config" --file "$b/.config" \
    --set-str CONFIG_LOCALVERSION "$localver" \
    -d CONFIG_LOCALVERSION_AUTO \
    --set-str CONFIG_INITRAMFS_SOURCE "$cpio" \
    -e CONFIG_INITRAMFS_COMPRESSION_GZIP

make -C "$k" O="$b" ARCH=arm64 CROSS_COMPILE="$cc_prefix" LOCALVERSION= olddefconfig
make -C "$k" O="$b" ARCH=arm64 CROSS_COMPILE="$cc_prefix" LOCALVERSION= \
    -j"$(nproc)" Image modules qcom/sm8550-oneplus-salami.dtb
cat "$b/arch/arm64/boot/dts/qcom/sm8550-oneplus-salami.dtb" >> "$b/arch/arm64/boot/Image"

rm -rf "$o"
mkdir -p "$o"
sh "$here/tools/package-kernel.sh" "$k" "$b" "$o" 1
