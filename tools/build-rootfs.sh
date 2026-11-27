#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Build the Ubuntu 26.04 arm64 command-line rootfs tar. Run as real root on an
# x86 host with qemu-user-static binfmt (F flag) and mmdebstrap.
#   build-rootfs.sh OUT KERNEL_OUT AUTHORIZED_KEYS USER RMTFS_DEB
set -eu
[ "$#" -eq 5 ] || { echo "usage: $0 OUT KERNEL_OUT AUTHORIZED_KEYS USER RMTFS_DEB" >&2; exit 2; }
out=$1 kout=$2 keys=$3 user=$4 rmtfs_deb=$(realpath "$5")
here=$(cd "$(dirname "$0")/.." && pwd)
for path in "$out" "$kout" "$keys" "$rmtfs_deb" "$here"; do
    case "$path" in *[!a-zA-Z0-9_./+-]*) echo "unsupported path characters: $path" >&2; exit 2;; esac
done
case "$user" in ''|[!a-z_]*|*[!a-z0-9_-]*) echo "invalid username: $user" >&2; exit 2;; esac
mirror=https://ports.ubuntu.com/ubuntu-ports
comp='main restricted universe'

[ ! -e "$out/root" ] || { echo "$out/root exists" >&2; exit 1; }
mkdir -p "$out"

rm -rf "$out/pkg"
sh "$here/tools/build-device-deb.sh" "$out/pkg"
cp "$rmtfs_deb" "$out/pkg/rmtfs.deb"

# check/qemu needs arch-test; the chroot steps below fail loudly without working binfmt.
# mmdebstrap skips Recommends by default, which drops dbus, logind and systemd-resolved; install
# them as a normal Ubuntu install would.
mmdebstrap --mode=root --arch=arm64 --variant=apt --components=main,restricted,universe --skip=check/qemu \
    --aptopt='APT::Install-Recommends "true"' \
    --include=ubuntu-minimal,ubuntu-keyring,systemd-zram-generator,systemd-oomd,irqbalance,rtkit,mobile-broadband-provider-info,iw,openssh-server,python3,ca-certificates,curl,less,bash-completion,htop,zstd,rmtfs,tqftpserv,qrtr-tools,linux-firmware-qualcomm-wireless,wireless-regdb,linux-firmware-qualcomm-graphics,usb-modeswitch,bluez,dmsetup \
    --customize-hook="copy-in $out/pkg/salami-device.deb /tmp" \
    --customize-hook="copy-in $out/pkg/rmtfs.deb /tmp" \
    --customize-hook='chroot "$1" dpkg -i /tmp/rmtfs.deb /tmp/salami-device.deb && rm "$1/tmp/rmtfs.deb" "$1/tmp/salami-device.deb"' \
    --customize-hook="sh '$here/tools/rootfs-customize.sh' \"\$1\" '$kout' '$keys' '$user'" \
    resolute "$out/root" \
    "deb $mirror resolute $comp" \
    "deb $mirror resolute-updates $comp" \
    "deb $mirror resolute-security $comp"

chroot "$out/root" dpkg-query -W -f '${Package}\t${Version}\t${Architecture}\n' > "$out/packages.tsv"
tar --xattrs --xattrs-include='*' --numeric-owner --sort=name -cpf "$out/rootfs.tar" -C "$out/root" .
sha256sum "$out/rootfs.tar" "$out/pkg/salami-device.deb" "$out/pkg/rmtfs.deb" > "$out/SHA256SUMS"
cat "$out/SHA256SUMS"
