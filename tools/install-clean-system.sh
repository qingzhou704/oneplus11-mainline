#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Install a clean OnePlus 11 Ubuntu desktop rootfs archive onto pre-created
# PARTLABEL=linux_root and PARTLABEL=linux_home from the RAM maintenance shell.
#
# Safety invariants:
# - Never creates, deletes, or resizes GPT partitions.
# - Never opens or writes stock firmware/calibration/boot partitions (super,
#   modem*, fsg, fsc, persist, oplus*, boot*, init_boot*, vendor_boot*).
# - Verifies the extracted rootfs has no seeded ordinary user, an empty
#   /etc/machine-id, and GDM InitialSetupEnable=true before succeeding.
#
# Usage inside the RAM maintenance shell (after `touch /run/keep`):
#   sh install-clean-system.sh ROOTFS_TAR_XZ [FACTORY_BT_MAC]
set -eu

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || {
    echo "usage: $0 ROOTFS_TAR_XZ [FACTORY_BT_MAC]" >&2
    exit 2
}
[ "$(id -u)" = 0 ] || { echo "must run as root in maintenance environment" >&2; exit 2; }
tarball=$1
bt_mac=${2:-}
[ -f "$tarball" ] || { echo "missing rootfs archive: $tarball" >&2; exit 2; }

if [ -n "$bt_mac" ]; then
    printf '%s\n' "$bt_mac" | grep -Eq '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' || {
        echo "invalid Bluetooth MAC format (expected XX:XX:XX:XX:XX:XX): $bt_mac" >&2
        exit 2
    }
    case "$(printf '%s' "$bt_mac" | tr 'A-F' 'a-f')" in
        00:00:00:00:00:00|ff:ff:ff:ff:ff:ff)
            echo "refusing all-zero or broadcast Bluetooth MAC" >&2
            exit 2
            ;;
    esac
fi

find_part() {
    want=$1
    found=""
    for u in /sys/class/block/*/uevent; do
        [ -f "$u" ] || continue
        if grep -Fqx "PARTNAME=$want" "$u"; then
            d=${u%/uevent}
            dev=/dev/${d##*/}
            [ -z "$found" ] || { echo "multiple partitions named $want" >&2; exit 1; }
            found=$dev
        fi
    done
    [ -n "$found" ] && [ -b "$found" ] || {
        echo "partition PARTNAME=$want not found; create linux_root and linux_home first" >&2
        exit 1
    }
    printf '%s\n' "$found"
}

FORBIDDEN="super modem_a modem_b modemst1 modemst2 fsg fsc persist oplusstanvbk_a oplusstanvbk_b oplusdycnvbk boot_a boot_b init_boot_a init_boot_b vendor_boot_a vendor_boot_b dtbo_a dtbo_b vbmeta_a vbmeta_b"
for p in $FORBIDDEN; do
    for u in /sys/class/block/*/uevent; do
        [ -f "$u" ] || continue
        if grep -Fqx "PARTNAME=$p" "$u"; then
            d=${u%/uevent}
            # Ensure stock partitions remain block-level read-only in RAM shell.
            blockdev --setro "/dev/${d##*/}" 2>/dev/null || true
        fi
    done
done

root_dev=$(find_part linux_root)
home_dev=$(find_part linux_home)
[ "$root_dev" != "$home_dev" ] || { echo "linux_root and linux_home resolve to same device" >&2; exit 1; }

printf 'Target linux_root : %s\nTarget linux_home : %s\nArchive           : %s\n' "$root_dev" "$home_dev" "$tarball"

blockdev --setrw "$root_dev"
blockdev --setrw "$home_dev"

# Use real e2fsprogs/GNU tar in maintenance image rather than BusyBox applets.
mkfs_ext4=/usr/sbin/mke2fs
[ -x "$mkfs_ext4" ] || mkfs_ext4=$(command -v mkfs.ext4)
gnu_tar=/usr/bin/tar
[ -x "$gnu_tar" ] || gnu_tar=$(command -v tar)

"$mkfs_ext4" -t ext4 -F -L linux_root "$root_dev"
"$mkfs_ext4" -t ext4 -F -L linux_home "$home_dev"

mnt=/mnt/clean-install
mkdir -p "$mnt"
cleanup() {
    umount "$mnt/home" 2>/dev/null || true
    umount "$mnt" 2>/dev/null || true
}
trap cleanup EXIT

mount -t ext4 "$root_dev" "$mnt"
mkdir -p "$mnt/home"
mount -t ext4 "$home_dev" "$mnt/home"

"$gnu_tar" --xattrs --xattrs-include='*' --acls --numeric-owner -xpf "$tarball" -C "$mnt"

if [ -n "$bt_mac" ]; then
    mkdir -p -m 755 "$mnt/var/lib/salami"
    (
        umask 077
        printf '%s\n' "$bt_mac" > "$mnt/var/lib/salami/bluetooth-address"
    )
    chmod 600 "$mnt/var/lib/salami/bluetooth-address"
fi

# Post-extract sanity & privacy checks before declaring success.
[ -x "$mnt/sbin/init" ] || { echo "extracted rootfs is missing /sbin/init" >&2; exit 1; }
[ ! -s "$mnt/etc/machine-id" ] || { echo "/etc/machine-id must be empty before first boot" >&2; exit 1; }
awk -F: '$3 >= 1000 && $3 < 60000 { exit 1 }' "$mnt/etc/passwd" || {
    echo "unexpected pre-seeded ordinary user in /etc/passwd" >&2
    exit 1
}
grep -Eq '^[[:space:]]*InitialSetupEnable[[:space:]]*=[[:space:]]*true' "$mnt/etc/gdm3/custom.conf" || {
    echo "GDM InitialSetupEnable=true missing in /etc/gdm3/custom.conf" >&2
    exit 1
}

sync
cleanup
trap - EXIT
echo "CLEAN_SYSTEM_INSTALL_OK: flash matching boot.img to boot_a and reboot into GNOME Initial Setup."
