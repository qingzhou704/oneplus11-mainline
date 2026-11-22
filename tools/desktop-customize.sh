#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# mmdebstrap desktop customize hook. Only operates in the newly created build root.
set -eu
[ "$#" -eq 2 ] || { echo 'usage: desktop-customize.sh ROOT HTTPS_MIRROR' >&2; exit 2; }
r=$(realpath -e "$1")
mirror=$2
[ "$r" != / ] && [ -f "$r/tmp/inputs/kernel.deb" ] && [ -f "$r/etc/debian_version" ] || exit 2
printf 'Customizing checked build root: %s\n' "$r"
# Explicitly deny runtime service starts during the additional APT installation.
# The device postinst also guards its direct systemctl/udevadm calls.
own_policy=false
if [ ! -e "$r/usr/sbin/policy-rc.d" ]; then
    printf '#!/bin/sh\nexit 101\n' > "$r/usr/sbin/policy-rc.d"
    chmod 755 "$r/usr/sbin/policy-rc.d"
    own_policy=true
fi
install -d "$r/etc/apt/keyrings" "$r/etc/apt/preferences.d"
install -m 644 "$r/tmp/inputs/mozilla.asc" "$r/etc/apt/keyrings/mozilla.asc"
cat > "$r/etc/apt/sources.list.d/mozilla.sources" <<'EOF'
Types: deb
URIs: https://packages.mozilla.org/apt
Suites: mozilla
Components: main
Signed-By: /etc/apt/keyrings/mozilla.asc
EOF
cat > "$r/etc/apt/preferences.d/salami-desktop" <<'EOF'
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 1000

Package: firefox firefox-*
Pin: release o=Ubuntu
Pin-Priority: -1

Package: snapd
Pin: version *
Pin-Priority: -1

Package: gnome-initial-setup
Pin: version /\+salami[0-9]+$/
Pin-Priority: 1001
EOF
chroot "$r" apt-get update \
    -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/mozilla.sources \
    -o Dir::Etc::sourceparts=- \
    -o APT::Get::List-Cleanup=0
# Cache via native host curl with HTTP/1.1 and resume support: both APT TLS
# and curl HTTP/2 have truncated this large archive on the current route.
# Size and SHA256 are checked against signed APT data.
for deb in "$r/tmp/inputs"/firefox_*.deb "$r/tmp/inputs"/firefox-l10n-zh-cn_*.deb; do
    [ ! -f "$deb" ] || cp "$deb" "$r/var/cache/apt/archives/"
done
python3 "$r/tmp/inputs/cache-mozilla-debs.py" "$r"
extra_debs=""
for opt_deb in /tmp/inputs/qcom-va-driver.deb /tmp/inputs/gnome-remote-desktop.deb; do
    [ ! -f "$r$opt_deb" ] || extra_debs="$extra_debs $opt_deb"
done
# shellcheck disable=SC2086
chroot "$r" env DEBIAN_FRONTEND=noninteractive apt-get -y --no-install-recommends install \
    /tmp/inputs/kernel.deb /tmp/inputs/rmtfs.deb /tmp/inputs/device.deb \
    /tmp/inputs/gnome-initial-setup.deb /tmp/inputs/passwordless-policy.deb $extra_debs firefox firefox-l10n-zh-cn \
    wpasupplicant modemmanager libpam-gnome-keyring at-spi2-core x11-xkb-utils zenity \
    alsa-ucm-conf alsa-utils gstreamer1.0-libav gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    language-pack-gnome-zh-hans

printf 'oneplus11\n' > "$r/etc/hostname"
cat > "$r/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 oneplus11
::1 localhost ip6-localhost ip6-loopback
EOF
# A missing home partition must not silently create the first account on the wrong volume.
cat > "$r/etc/fstab" <<'EOF'
PARTLABEL=linux_root / ext4 defaults,errors=remount-ro,x-gvfs-show,x-gvfs-name=Linux系统 0 1
PARTLABEL=linux_home /home ext4 defaults,x-gvfs-show,x-gvfs-name=个人文件 0 2
EOF
install -d "$r/etc/systemd/system/gdm.service.d" "$r/etc/ssh/sshd_config.d"
cat > "$r/etc/systemd/system/gdm.service.d/50-salami-home.conf" <<'EOF'
[Unit]
RequiresMountsFor=/home
EOF
# Use GDM's upstream no-user path, not a fixed account or a network installer.
# The installed Ubuntu GDM configuration is updated narrowly below.
python3 - "$r" <<'PY'
import configparser
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
p = root / 'etc/gdm3/custom.conf'
c = configparser.ConfigParser(interpolation=None, strict=False)
c.optionxform = str
if p.exists():
    c.read(p)
if not c.has_section('daemon'):
    c.add_section('daemon')
c.set('daemon', 'InitialSetupEnable', 'true')
c.set('daemon', 'AutomaticLoginEnable', 'false')
c.set('daemon', 'DefaultSession', 'ubuntu.desktop')
with p.open('w') as f:
    c.write(f)
PY
install -d "$r/etc/gnome-initial-setup"
cat > "$r/etc/gnome-initial-setup/vendor.conf" <<'EOF'
[pages]
skip=ubuntu_pro;ubuntu_insights;software;apps;timezone;
EOF
chroot "$r" systemctl enable gdm.service
chroot "$r" systemctl set-default graphical.target
chroot "$r" systemctl enable NetworkManager.service systemd-resolved.service ModemManager.service nftables.service
cat > "$r/etc/nftables.conf" <<'EOF'
#!/usr/sbin/nft -f
# Default host firewall for OnePlus 11 Linux: blocks unsolicited inbound WAN/5G
# traffic while allowing loopback, DHCP, ICMP/ICMPv6, local LAN discovery, and
# flood-limited SSH/RDP once an administrator explicitly enables remote access.
flush ruleset

table inet filter {
	chain input {
		type filter hook input priority filter; policy drop;
		iif lo accept
		ct state established,related accept
		ct state invalid drop
		ip protocol icmp accept
		ip6 nexthdr icmpv6 accept
		udp sport 67 udp dport 68 accept
		iifname "usb0" udp dport 67 accept
		tcp dport 22 ct count over 24 reject
		tcp dport 22 accept
		ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } tcp dport { 3389, 3390 } ct count over 16 drop
		ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } tcp dport { 3389, 3390 } accept
		ip saddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } udp dport 5353 accept
	}
	chain forward {
		type filter hook forward priority filter; policy drop;
		iifname "docker0" accept
		oifname "docker0" accept
	}
	chain output {
		type filter hook output priority filter; policy accept;
	}
}
EOF
chmod 0755 "$r/etc/nftables.conf"
chroot "$r" systemctl --global enable pipewire.socket pipewire-pulse.socket wireplumber.service
chroot "$r" systemctl mask systemd-firstboot.service
# Disable both service and socket activation. No remote credentials are shipped.
for unit in ssh.service ssh.socket salami-ssh-hostkeys.service salami-debug-shell.socket \
    gnome-remote-desktop.service gnome-remote-desktop-headless.service; do
    chroot "$r" systemctl disable "$unit" 2>/dev/null || true
done
chroot "$r" systemctl mask ssh.service ssh.socket salami-debug-shell.socket
# A user can unmask/enable SSH later; that action generates this device's host keys.
install -d "$r/etc/systemd/system/ssh.service.d"
cat > "$r/etc/systemd/system/ssh.service.d/50-salami-hostkeys.conf" <<'EOF'
[Unit]
Requires=salami-ssh-hostkeys.service
After=salami-ssh-hostkeys.service
EOF
# No GDM auto-login, no seeded ordinary user, no passwordless sudo.
awk -F: '$3 >= 1000 && $3 < 60000 { found=1; print "unexpected ordinary user: " $1 > "/dev/stderr" } END { exit found }' "$r/etc/passwd"
chroot "$r" passwd -l root
printf 'zh_CN.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\n' > "$r/etc/locale.gen"
chroot "$r" locale-gen
chroot "$r" update-locale LANG=zh_CN.UTF-8
install -d "$r/etc/default"
cat > "$r/etc/default/keyboard" <<'EOF'
XKBMODEL="pc105"
XKBLAYOUT="us"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
EOF
# Regional default for this Chinese desktop image, not a language-to-zone inference.
# Users may change it later in Settings; no first-setup map or network requirement.
[ -f "$r/usr/share/zoneinfo/Asia/Shanghai" ]
ln -snf /usr/share/zoneinfo/Asia/Shanghai "$r/etc/localtime"
printf 'Asia/Shanghai\n' > "$r/etc/timezone"
cat > "$r/usr/share/glib-2.0/schemas/90-salami-desktop.gschema.override" <<'EOF'
[org.gnome.desktop.input-sources]
sources=[('xkb', 'us'), ('ibus', 'libpinyin')]

[org.gnome.desktop.interface]
clock-format='24h'

[org.gnome.settings-daemon.plugins.power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
EOF
chroot "$r" glib-compile-schemas --strict /usr/share/glib-2.0/schemas
# The following are exclusively build-root artifacts; root was resolved and checked above.
rm -f "$r"/etc/ssh/ssh_host_*
if $own_policy; then rm -f "$r/usr/sbin/policy-rc.d"; fi
rm -rf "$r/tmp/inputs"
chroot "$r" apt-get clean
: > "$r/etc/machine-id"
# dbus must share the per-target machine identity, not a value made by QEMU/chroot.
rm -f "$r/var/lib/dbus/machine-id"
ln -s /etc/machine-id "$r/var/lib/dbus/machine-id"
find "$r/var/log" -type f -exec truncate -s 0 {} +
# Replace the builder's transient sources with explicit persistent signed sources.
rm -f "$r/etc/apt/sources.list"
cat > "$r/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: $mirror
Suites: resolute resolute-updates resolute-security
Components: main restricted universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
