#!/bin/sh
# Configure an existing Ubuntu GNOME account for Simplified Chinese.
# Run as root: configure-chinese-desktop.sh USER [TIMEZONE]
set -eu
user=${1:?desktop username}
tz=${2:-Asia/Shanghai}
id "$user" >/dev/null
usermod -aG render "$user"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends language-pack-zh-hans language-pack-gnome-zh-hans \
    fonts-noto-cjk ibus-libpinyin
sed -i 's/^# *zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen
locale-gen zh_CN.UTF-8
update-locale LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh
timedatectl set-timezone "$tz"
uid=$(id -u "$user")
busctl call org.freedesktop.Accounts "/org/freedesktop/Accounts/User$uid" \
    org.freedesktop.Accounts.User SetLanguage s zh_CN.UTF-8
runuser -u "$user" -- dbus-run-session -- gsettings set org.gnome.system.locale region zh_CN.UTF-8
runuser -u "$user" -- dbus-run-session -- gsettings set org.gnome.desktop.input-sources sources \
    "[('xkb', 'us'), ('ibus', 'libpinyin')]"
runuser -u "$user" -- dbus-run-session -- gsettings set org.gnome.desktop.input-sources mru-sources \
    "[('ibus', 'libpinyin'), ('xkb', 'us')]"
localectl status
busctl get-property org.freedesktop.Accounts "/org/freedesktop/Accounts/User$uid" \
    org.freedesktop.Accounts.User Language
runuser -u "$user" -- dbus-run-session -- gsettings get org.gnome.desktop.input-sources sources
