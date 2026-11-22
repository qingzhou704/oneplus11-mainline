#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Run as root on an ARM64 host or an x86 Linux host with ARM64 binfmt F support.
# A new Linux-filesystem output directory is required. Never accesses a phone.
set -eu
[ "$#" -eq 3 ] || { echo "usage: $0 OUT KERNEL_DEB RMTFS_DEB" >&2; exit 2; }
[ "$(id -u)" = 0 ] || { echo 'real root is required by mmdebstrap' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out=$(realpath -m -- "$1")
kernel=$(realpath -e -- "$2")
rmtfs=$(realpath -e -- "$3")
case "$out" in /mnt/*|/|/root|/tmp|/var|/home) echo 'use a new dedicated Linux-filesystem output directory' >&2; exit 2;; esac
[ ! -e "$out" ] || { echo "refusing existing output: $out" >&2; exit 2; }
# Hook arguments are shell-quoted. Restrict paths rather than accepting shell syntax.
for path in "$out" "$kernel" "$rmtfs" "$here"; do
    case "$path" in *[!a-zA-Z0-9_./+-]*) echo "unsupported path characters: $path" >&2; exit 2;; esac
done
[ "$(dpkg-deb -f "$kernel" Architecture)" = arm64 ]
case "$(dpkg-deb -f "$kernel" Package)" in linux-image-*-salami*) ;; *) echo 'not a salami kernel package' >&2; exit 2;; esac
[ "$(dpkg-deb -f "$rmtfs" Package)" = rmtfs ]
[ "$(dpkg-deb -f "$rmtfs" Architecture)" = arm64 ]
dpkg --compare-versions "$(dpkg-deb -f "$rmtfs" Version)" ge '1.1.1-2+salami1'
# The optional-password GUI must match the local opt-in policy; fail rather
# than silently shipping the unpatched mandatory-password wizard.
gis=$(realpath -e "${GIS_DEB:?set GIS_DEB to the reviewed optional-password ARM64 package}")
[ "$(dpkg-deb -f "$gis" Package)" = gnome-initial-setup ]
[ "$(dpkg-deb -f "$gis" Architecture)" = arm64 ]
case "$(dpkg-deb -f "$gis" Version)" in *+salami*) ;; *) echo 'patched GIS package required' >&2; exit 2;; esac
mirror=${UBUNTU_MIRROR:-https://ports.ubuntu.com/ubuntu-ports}
case "$mirror" in https://*[!a-zA-Z0-9_./:+-]*|'') echo 'invalid HTTPS mirror' >&2; exit 2;; https://*) ;; *) echo 'HTTPS mirror required' >&2; exit 2;; esac
for cmd in mmdebstrap qemu-aarch64-static dpkg-deb aarch64-linux-gnu-gcc alsatplg m4 curl gpg python3 xz; do
    command -v "$cmd" >/dev/null || { echo "missing tool: $cmd" >&2; exit 2; }
done
printf 'New output: %s\nKernel input: %s\nRmtfs input: %s\nMirror: %s\n' "$out" "$kernel" "$rmtfs" "$mirror"
mkdir -p "$out/inputs"
date -u +%FT%TZ > "$out/build-start.txt"
printf '%s\n' "$mirror" > "$out/ubuntu-mirror.txt"
cp "$kernel" "$out/inputs/kernel.deb"
cp "$rmtfs" "$out/inputs/rmtfs.deb"
cp "$gis" "$out/inputs/gnome-initial-setup.deb"
if [ -n "${QCOM_VA_DEB:-}" ]; then
    qva=$(realpath -e -- "$QCOM_VA_DEB")
    [ "$(dpkg-deb -f "$qva" Architecture)" = arm64 ]
    cp "$qva" "$out/inputs/qcom-va-driver.deb"
fi
if [ -n "${GRD_DEB:-}" ]; then
    grd=$(realpath -e -- "$GRD_DEB")
    [ "$(dpkg-deb -f "$grd" Package)" = gnome-remote-desktop ]
    [ "$(dpkg-deb -f "$grd" Architecture)" = arm64 ]
    cp "$grd" "$out/inputs/gnome-remote-desktop.deb"
fi
sh "$here/tools/build-passwordless-policy.sh" "$out/passwordless-build"
cp "$out/passwordless-build/salami-desktop-passwordless.deb" "$out/inputs/passwordless-policy.deb"
# build-device-deb removes its staging subtree; this path is new and checked above.
sh "$here/tools/build-device-deb.sh" "$out/device-build"
cp "$out/device-build/salami-device.deb" "$out/inputs/device.deb"
cp "$here/rootfs/desktop/packages.txt" "$out/inputs/packages.txt"
cp "$here/tools/desktop-customize.sh" "$out/inputs/desktop-customize.sh"
cp "$here/tools/build-desktop-rootfs.sh" "$out/inputs/build-desktop-rootfs.sh"
mkdir -p "$out/validation/tools" "$out/validation/rootfs/desktop"
cp "$here/tools/verify-desktop-rootfs.py" "$out/validation/tools/verify-desktop-rootfs.py"
cp "$here/tools/cache-mozilla-debs.py" "$out/inputs/cache-mozilla-debs.py"
# Optional local browser cache; every file is rechecked against signed metadata
# by cache-mozilla-debs.py before APT is allowed to consume it.
if [ -n "${MOZILLA_CACHE_DIR:-}" ]; then
    cache=$(realpath -e "$MOZILLA_CACHE_DIR")
    [ -d "$cache" ] || exit 2
    for deb in "$cache"/firefox_*.deb "$cache"/firefox-l10n-zh-cn_*.deb; do
        [ ! -f "$deb" ] || cp "$deb" "$out/inputs/"
    done
fi
cp "$here/rootfs/desktop/packages.txt" "$out/validation/rootfs/desktop/packages.txt"
curl --fail --location --connect-timeout 20 --max-time 120 \
    https://packages.mozilla.org/apt/repo-signing-key.gpg -o "$out/inputs/mozilla.asc"
fingerprint=$(gpg --batch --show-keys --with-colons "$out/inputs/mozilla.asc" | awk -F: '$1=="fpr" {print $10; exit}')
[ "$fingerprint" = 35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3 ] || {
    echo "unexpected Mozilla signing key: $fingerprint" >&2; exit 1;
}
printf '%s\n' "$fingerprint" > "$out/mozilla-key-fingerprint.txt"
(cd "$out" && sha256sum inputs/* validation/tools/* validation/rootfs/desktop/*) > "$out/INPUT-SHA256SUMS"
packages=$(awk '!/^#/ && NF {print $1}' "$out/inputs/packages.txt" | paste -sd, -)
mmdebstrap --mode=root --arch=arm64 --variant=apt --skip=check/qemu \
    --components=main,restricted,universe --aptopt='APT::Install-Recommends "false"' \
    --aptopt='Acquire::Retries "3"' \
    --include="$packages" \
    --customize-hook="copy-in $out/inputs /tmp" \
    --customize-hook="sh '$out/inputs/desktop-customize.sh' \"\$1\" '$mirror'" \
    resolute "$out/root" \
    "deb $mirror resolute main restricted universe" \
    "deb $mirror resolute-updates main restricted universe" \
    "deb $mirror resolute-security main restricted universe"
python3 "$out/validation/tools/verify-desktop-rootfs.py" "$out/root" > "$out/content-verification.txt"
chroot "$out/root" dpkg --audit > "$out/dpkg-audit.txt"
[ ! -s "$out/dpkg-audit.txt" ] || { echo 'dpkg audit is not empty' >&2; exit 1; }
chroot "$out/root" apt-get check > "$out/apt-check.txt" 2>&1
# mmdebstrap uses the builder's resolver during installation. Replace it only
# after network-dependent checks and its own cleanup have finished.
[ "$(realpath -e "$out/root/etc")" = "$out/root/etc" ]
rm -f "$out/root/etc/resolv.conf"
ln -s ../run/systemd/resolve/stub-resolv.conf "$out/root/etc/resolv.conf"
chroot "$out/root" dpkg-query -W -f '${Package}\t${Version}\t${Architecture}\n' > "$out/packages.tsv"
# The kernel package embeds exactly the corresponding boot image and module tree.
set -- "$out/root/boot/boot.img-"*
[ "$#" -eq 1 ] && [ -f "$1" ]
release=${1##*/boot.img-}
printf '%s\n' "$release" > "$out/kernel-release.txt"
cp "$1" "$out/boot.img"
# Read-only verification must precede packaging; package names are written only on success.
tar --xattrs --xattrs-include='*' --acls --numeric-owner --sort=name \
    -I 'xz -T0 -3' -cpf "$out/rootfs.tar.xz.partial" -C "$out/root" .
[ "$(realpath -m "$out/rootfs.tar.xz.partial")" = "$out/rootfs.tar.xz.partial" ]
mv "$out/rootfs.tar.xz.partial" "$out/rootfs.tar.xz"
(cd "$out" && sha256sum rootfs.tar.xz boot.img packages.tsv kernel-release.txt INPUT-SHA256SUMS) > "$out/SHA256SUMS"
date -u +%FT%TZ > "$out/build-end.txt"
printf '%s\n' 'OFFLINE BUILD VERIFIED; SECOND-DEVICE FIRST BOOT NOT TESTED' > "$out/BUILD-STATUS.txt"
cat "$out/SHA256SUMS"
