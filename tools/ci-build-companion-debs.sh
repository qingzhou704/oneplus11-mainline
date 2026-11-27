#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Build Ubuntu 26.04 (resolute) ARM64 companion packages from upstream sources
# inside an isolated native ARM64 resolute buildroot:
#   - rmtfs (+salami1 OEM NV mapping)
#   - qcom-va-driver (1.1.1-1 Iris3 VA-API backend)
#   - gnome-initial-setup (+salami1 optional password wizard)
#   - gnome-remote-desktop (+salami3 implicit-sync + VA-API inband headers + QP)
# usage: sudo sh tools/ci-build-companion-debs.sh OUTPUT_DIR
set -eu
[ "$(id -u)" = 0 ] || { echo "root required for mmdebstrap buildroot" >&2; exit 2; }
[ "$(uname -m)" = aarch64 ] || { echo "native aarch64 host required" >&2; exit 2; }
out=$(realpath -m "${1:?output directory}")
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mirror=${UBUNTU_MIRROR:-https://ports.ubuntu.com/ubuntu-ports}

work=/var/tmp/salami-companion-buildroot
rm -rf "$work" "$out"
mkdir -p "$work" "$out"

mmdebstrap --mode=root --arch=arm64 --variant=buildd \
    --components=main,restricted,universe \
    --include=dpkg-dev,devscripts,debhelper,meson,ninja-build,pkg-config,git,ca-certificates,curl,patch,python3,libqrtr-dev,libudev-dev,libva-dev,libdrm-dev,libgbm-dev \
    resolute "$work/root" \
    "deb $mirror resolute main restricted universe" \
    "deb $mirror resolute-updates main restricted universe" \
    "deb $mirror resolute-security main restricted universe"

cat > "$work/root/etc/apt/sources.list.d/ubuntu-src.sources" <<EOF
Types: deb-src
URIs: $mirror
Suites: resolute resolute-updates resolute-security
Components: main restricted universe
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF

cp -r "$here/patches" "$here/tools" "$work/root/tmp/"
mount -t proc proc "$work/root/proc"
cleanup() {
    umount "$work/root/proc" 2>/dev/null || true
    rm -rf "$work"
}
trap cleanup EXIT

chroot "$work/root" sh -eux <<'CHROOT_EOF'
export DEBIAN_FRONTEND=noninteractive
export DEBEMAIL="noreply@localhost"
export DEBFULLNAME="OnePlus 11 mainline port"
apt-get update
mkdir -p /tmp/out /tmp/work

# 1. rmtfs (+salami1 with OEM NV mappings)
cd /tmp/work
curl -fsSL https://github.com/linux-msm/rmtfs/archive/291e16dbd1f1c2cfc660ea7f77767571185e1a3a.tar.gz -o rmtfs-src.tar.gz
printf '%s  %s\n' cfaae038a5f1f43a8f15bef2a4ec26ca047746b9d2ff64e6ab43ad3cb135a033 rmtfs-src.tar.gz | sha256sum -c -
apt-get download rmtfs
base_rmtfs=$(ls rmtfs_*.deb | head -n 1)
mkdir rmtfs-src && tar -xzf rmtfs-src.tar.gz -C rmtfs-src --strip-components=1
make -C rmtfs-src -j"$(nproc)"
dpkg-deb -R "$base_rmtfs" rmtfs-pkg
install -m 755 rmtfs-src/rmtfs rmtfs-pkg/usr/bin/rmtfs
sed -i 's/^Version: \(.*\)$/Version: \1+salami1/' rmtfs-pkg/DEBIAN/control
(cd rmtfs-pkg && find . -type f ! -path './DEBIAN/*' -print0 | LC_ALL=C sort -z | xargs -0 md5sum > DEBIAN/md5sums)
dpkg-deb --root-owner-group -Zxz --build rmtfs-pkg /tmp/out/rmtfs.deb

# 2. qcom-va-driver (1.1.1-1)
cd /tmp/work
git clone https://github.com/radxa-pkg/qcom-va-driver.git
cd qcom-va-driver
git checkout 0980a1de
apt-get build-dep -y .
DEB_BUILD_OPTIONS="parallel=$(nproc) nocheck" dpkg-buildpackage -b -uc -us
qva_deb=$(ls /tmp/work/qcom-va-driver_*_arm64.deb | head -n 1)
cp "$qva_deb" /tmp/out/qcom-va-driver.deb

# 3. gnome-initial-setup (+salami optional password)
mkdir -p /tmp/work/gis && cd /tmp/work/gis
apt-get build-dep -y gnome-initial-setup
apt-get source gnome-initial-setup
cd gnome-initial-setup-*
case "$(dpkg-parsechangelog -S Version)" in
    50.0-*) ;;
    *) echo "unexpected gnome-initial-setup upstream version: $(dpkg-parsechangelog -S Version)" >&2; exit 1 ;;
esac
patch --fuzz=0 -p1 < /tmp/patches/gnome-initial-setup-50.0-optional-password.patch
dch --local +salami "Allow optional empty password on local initial setup"
DEB_BUILD_OPTIONS="parallel=$(nproc) nocheck" dpkg-buildpackage -b -uc -us
cp /tmp/work/gis/gnome-initial-setup_*+salami*_arm64.deb /tmp/out/gnome-initial-setup.deb

# 4. gnome-remote-desktop (+salami implicit-sync + VA-API inband + QP)
mkdir -p /tmp/work/grd && cd /tmp/work/grd
apt-get build-dep -y gnome-remote-desktop
apt-get source gnome-remote-desktop
cd gnome-remote-desktop-*
case "$(dpkg-parsechangelog -S Version)" in
    50.2-*) ;;
    *) echo "unexpected gnome-remote-desktop upstream version: $(dpkg-parsechangelog -S Version)" >&2; exit 1 ;;
esac
patch --fuzz=0 -p1 < /tmp/patches/gnome-remote-desktop-50.2-implicit-sync.patch
patch --fuzz=0 -p1 < /tmp/patches/gnome-remote-desktop-50.2-vaapi-inband-headers.patch
patch --fuzz=0 -p1 < /tmp/patches/gnome-remote-desktop-50.2-vaapi-qp-env.patch
dch --local +salami "Add DMABUF implicit-sync fallback and Qualcomm Iris VA-API hardware encoding"
DEB_BUILD_OPTIONS="parallel=$(nproc) nocheck" dpkg-buildpackage -b -uc -us
cp /tmp/work/grd/gnome-remote-desktop_*+salami*_arm64.deb /tmp/out/gnome-remote-desktop.deb
CHROOT_EOF

cp "$work/root/tmp/out/"*.deb "$out/"
sha256sum "$out/"*.deb
