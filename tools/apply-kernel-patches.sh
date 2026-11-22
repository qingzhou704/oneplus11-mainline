#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Apply the complete OnePlus 11 (salami) kernel patch series in exact order
# onto base commit f2941a66b02ad4e71ca2b219368bac57c8bf8c50 (linux-perpetua).
set -eu
k=$(realpath "${1:?kernel source tree}")
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

for p in \
    "$here/patches/kernel-064-salami-bringup.patch" \
    "$here/patches/kernel-066-spmi-temp-alarm.patch" \
    "$here/patches/kernel-067-iris-video.patch" \
    "$here/patches/kernel-067-v2-vooc-bbr.patch" \
    "$here/patches/kernel-067-v3-display-hbm-netfilter.patch" \
    "$here/patches/kernel-067-v4-touch-vooc-modules.patch" \
    "$here/patches/kernel-068-linux-7.3.5-rollup.patch"
do
    [ -f "$p" ] || { echo "missing patch: $p" >&2; exit 2; }
    GIT_COMMITTER_NAME="OnePlus 11 mainline port" \
    GIT_COMMITTER_EMAIL="noreply@localhost" \
    git -C "$k" am "$p"
done

cp "$here/kernel/sm8550-oneplus-salami.dts" "$here/kernel"/sm8550-oneplus-salami*.dtsi \
    "$k/arch/arm64/boot/dts/qcom/"
mkdir -p "$k/devices/salami"
cp "$here/kernel/kernel.config" "$here/kernel/device" "$k/devices/salami/"
if [ -n "$(git -C "$k" status --porcelain)" ]; then
    git -C "$k" add -A
    GIT_AUTHOR_NAME="OnePlus 11 mainline port" \
    GIT_AUTHOR_EMAIL="noreply@localhost" \
    GIT_COMMITTER_NAME="OnePlus 11 mainline port" \
    GIT_COMMITTER_EMAIL="noreply@localhost" \
    git -C "$k" commit -m "arm64: dts: qcom: sync canonical salami device tree and config"
fi
