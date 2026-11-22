#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Usage: build-ramfs.sh BUSYBOX GEN_INIT_CPIO OUTPUT_DIR BUILD_ID [EXTRA_ROOT]
# EXTRA_ROOT: optional tree added on top (maintenance tools; /etc/maintenance selects that role).
set -eu
busybox=${1:?path to the ARM64 static BusyBox}
gen_init_cpio=${2:?path to the host gen_init_cpio}
output=${3:?output directory}
build_id=${4:?candidate build ID}
extra=${5:-}
integration=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

mkdir -p "$output"
output=$(CDPATH= cd -- "$output" && pwd)
printf '%s\n' "$build_id" > "$output/build-id.txt"
cat > "$output/rootfs.list" <<EOF
dir /bin 0755 0 0
dir /dev 0755 0 0
dir /etc 0755 0 0
dir /proc 0755 0 0
dir /sys 0755 0 0
dir /run 0755 0 0
file /init $integration/initramfs/init 0755 0 0
file /bin/busybox $busybox 0755 0 0
file /bin/salami-usb-gadget $integration/rootfs/salami-device/usr/lib/salami/usb-gadget 0755 0 0
slink /bin/sh busybox 0777 0 0
nod /dev/console 0600 0 0 c 5 1
nod /dev/null 0666 0 0 c 1 3
file /etc/build-id $output/build-id.txt 0644 0 0
EOF
if [ -n "$extra" ]; then
    extra=$(CDPATH= cd -- "$extra" && pwd)
    (cd "$extra" && find . -mindepth 1 | sort) | while read -r p; do
        p=${p#.}
        case "$p" in /bin|/etc) continue ;; esac
        src=$extra$p
        mode=$(stat -c %a "$src")
        if [ -L "$src" ]; then
            echo "slink $p $(readlink "$src") 0777 0 0"
        elif [ -d "$src" ]; then
            echo "dir $p $mode 0 0"
        else
            echo "file $p $src $mode 0 0"
        fi
    done >> "$output/rootfs.list"
fi
"$gen_init_cpio" -t 0 "$output/rootfs.list" > "$output/firstboot.cpio"
sha256sum "$output/firstboot.cpio"
