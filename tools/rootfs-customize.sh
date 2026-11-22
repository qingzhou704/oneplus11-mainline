#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# mmdebstrap customize hook for build-rootfs.sh: ROOT KERNEL_OUT AUTHORIZED_KEYS USER
set -eu
r=$1 kout=$2 keys=$3 user=$4

echo oneplus11 > "$r/etc/hostname"
cat > "$r/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 oneplus11
::1 localhost ip6-localhost ip6-loopback
EOF
cat > "$r/etc/fstab" <<'EOF'
PARTLABEL=linux_root / ext4 defaults,errors=remount-ro,x-gvfs-show,x-gvfs-name=Linux系统 0 1
PARTLABEL=linux_home /home ext4 defaults,nofail,x-gvfs-show,x-gvfs-name=个人文件 0 2
EOF

rm -f "$r/etc/apt/sources.list"
cat > "$r/etc/apt/sources.list.d/ubuntu.sources" <<'EOF'
Types: deb
URIs: https://ports.ubuntu.com/ubuntu-ports
Suites: resolute resolute-updates resolute-security
Components: main restricted universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF

# Key-only account; home is created on linux_home at first login.
chroot "$r" useradd -M -u 1000 -s /bin/bash -G sudo,adm,render "$user"
chroot "$r" usermod -p '*' "$user"
install -d -m 755 "$r/etc/ssh/authorized_keys.d"
install -m 644 "$keys" "$r/etc/ssh/authorized_keys.d/$user"
echo "$user ALL=(ALL) NOPASSWD:ALL" > "$r/etc/sudoers.d/90-$user"
chmod 440 "$r/etc/sudoers.d/90-$user"
chroot "$r" pam-auth-update --enable mkhomedir

rm -f "$r"/etc/ssh/ssh_host_*
: > "$r/etc/machine-id"
# Locale, keymap, timezone and accounts are set above; the empty machine-id makes the first boot
# run systemd-firstboot, which would wait on a console nobody can type on.
ln -s /dev/null "$r/etc/systemd/system/systemd-firstboot.service"

# The kernel output directory's generated Makefile forwards to the source tree.
make -s -C "$kout" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    INSTALL_MOD_PATH="$r/usr" INSTALL_MOD_STRIP=1 modules_install
rm -f "$r"/usr/lib/modules/*/build "$r"/usr/lib/modules/*/source
