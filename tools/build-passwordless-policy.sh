#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Build opt-in local passwordless policy; does not enable it for any account.
set -eu
[ "$#" -eq 1 ] || { echo 'usage: build-passwordless-policy.sh NEW_OUT' >&2; exit 2; }
out=$(realpath -m "$1")
[ ! -e "$out" ] || { echo 'refuse existing output' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$out/pkg/DEBIAN"
cp -a "$here/rootfs/desktop-passwordless/." "$out/pkg/"
find "$out/pkg" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$out/pkg" -type f -name '*.pyc' -delete
find "$out/pkg" -type d -exec chmod 755 {} +
find "$out/pkg" -type f -exec chmod 644 {} +
chmod 755 "$out/pkg/usr/lib/salami/enable-passwordless-local"
chmod 440 "$out/pkg/etc/sudoers.d/50-salami-passwordless"
cat > "$out/pkg/DEBIAN/control" <<'EOF'
Package: salami-desktop-passwordless
Version: 0.2
Architecture: all
Maintainer: OnePlus 11 mainline port <noreply@localhost>
Depends: python3, accountsservice, libglib2.0-bin, sudo, polkitd, pkexec, passwd, systemd
Section: admin
Priority: optional
Description: Explicit first-setup opt-in local passwordless administration
 No accounts are preconfigured. Only the local first setup user can opt the
 newly created administrator into automatic login and passwordless management.
 Remote access is not enabled or modified.
EOF
cat > "$out/pkg/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -eu
if [ "$1" = configure ]; then
    systemd-sysusers /usr/lib/sysusers.d/salami-passwordless.conf
    /usr/sbin/visudo -cf /etc/sudoers.d/50-salami-passwordless
    systemctl enable salami-passwordless-reconcile.path salami-passwordless-reconcile.service
    if [ -d /run/systemd/system ] && ! systemd-detect-virt --quiet --chroot; then
        systemctl daemon-reload
        systemctl start salami-passwordless-reconcile.path salami-passwordless-reconcile.service
    fi
fi
EOF
chmod 755 "$out/pkg/DEBIAN/postinst"
dpkg-deb --root-owner-group -Zxz --build "$out/pkg" "$out/salami-desktop-passwordless.deb"
sha256sum "$out/salami-desktop-passwordless.deb"
