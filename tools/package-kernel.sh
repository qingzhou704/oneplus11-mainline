#!/bin/sh
# Package an already built salami kernel. Does not flash any partition.
# usage: package-kernel.sh KERNEL_TREE KERNEL_OUT OUTPUT_DIR [PACKAGE_VERSION]
# PACKAGE_VERSION (default 1): raise it to ship rebuilt modules for an already released kernel.
set -eu
k=$(realpath "${1:?kernel source}")
b=$(realpath "${2:?kernel build}")
o=$(realpath -m "${3:?package output}")
version=${4:-1}
workspace=$(cd "$(dirname "$0")/../../.." && pwd)
# kernel-changes.patch below is `git diff HEAD`, which omits untracked files.
untracked=$(git -C "$k" ls-files --others --exclude-standard)
[ -z "$untracked" ] || { printf 'untracked files would be missing from kernel-changes.patch:\n%s\n' "$untracked" >&2; exit 1; }
release=$(make -s -C "$k" O="$b" ARCH=arm64 LOCALVERSION= kernelrelease)
pkg=$b/package-$release-$version
test ! -e "$pkg"
mkdir -p "$pkg/boot" "$pkg/DEBIAN" "$o/evidence"
cp "$b/arch/arm64/boot/Image" "$o/Image"
cp "$b/.config" "$o/kernel.config"
cp "$k/arch/arm64/boot/dts/qcom/sm8550-oneplus-salami.dts" "$o/"
find "$k/arch/arm64/boot/dts/qcom" -maxdepth 1 -name 'sm8550-oneplus-salami*.dtsi' -exec cp {} "$o/" \;
mkbootimg=${MKBOOTIMG:-$workspace/sources/aosp-mkbootimg/mkbootimg.py}
[ -e "$mkbootimg" ] || mkbootimg=$(command -v mkbootimg || true)
[ -n "$mkbootimg" ] && [ -e "$mkbootimg" ] || { echo "mkbootimg not found; install mkbootimg or set MKBOOTIMG" >&2; exit 2; }
avbtool=${AVBTOOL:-$workspace/sources/aosp-avb/avbtool.py}
[ -e "$avbtool" ] || avbtool=$(command -v avbtool || true)
[ -n "$avbtool" ] && [ -e "$avbtool" ] || { echo "avbtool not found; install avb or set AVBTOOL" >&2; exit 2; }
# Header versions, partition size, salt and props match OnePlus 11's stock boot_a AVB footer.
python3 "$mkbootimg" --header_version 4 --kernel "$o/Image" \
    --os_version 13.0.0 --os_patch_level 2026-04 --output "$o/boot.img"
python3 "$avbtool" add_hash_footer --image "$o/boot.img" --partition_name boot \
    --partition_size 201326592 --algorithm NONE --salt d95f0c937d2fdf92096f4a6e9f813258 \
    --prop com.android.build.boot.os_version:13 \
    --prop 'com.android.build.boot.fingerprint:qti/kalama/kalama:13/TP1A.220905.001/1775634070652:user/release-keys' \
    --prop com.android.build.boot.security_patch:2026-04-01 \
    --prop com.android.build.boot.security_patch:2026-04-01
python3 "$avbtool" verify_image --image "$o/boot.img" > "$o/evidence/avb.txt"
make -s -C "$k" O="$b" ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" LOCALVERSION= \
    INSTALL_MOD_PATH="$pkg" INSTALL_MOD_STRIP=1 DEPMOD=true modules_install
rm -f "$pkg/lib/modules/$release/build"
cp "$o/boot.img" "$pkg/boot/boot.img-$release"
cp "$b/.config" "$pkg/boot/config-$release"
cp "$b/System.map" "$pkg/boot/System.map-$release"
cat > "$pkg/DEBIAN/control" <<EOF
Package: linux-image-$release
Version: $version
Architecture: arm64
Maintainer: OnePlus 11 mainline port <noreply@localhost>
Depends: kmod
Section: kernel
Priority: optional
Description: OnePlus 11 salami kernel and matching modules
 The boot image is installed under /boot. Deployment to boot_a is an
 explicit maintenance action; this package never flashes a partition.
EOF
cat > "$pkg/DEBIAN/postinst" <<EOF
#!/bin/sh
set -e
if [ "\$1" = configure ]; then
    depmod -a '$release'
fi
EOF
cat > "$pkg/DEBIAN/postrm" <<EOF
#!/bin/sh
set -e
if [ "\$1" = remove ] || [ "\$1" = purge ]; then
    rm -f '/lib/modules/$release'/modules.*
    rmdir '/lib/modules/$release' 2>/dev/null || true
fi
EOF
chmod 755 "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/postrm"
dpkg-deb --root-owner-group -Zzstd --build "$pkg" "$o/linux-image-$release.deb" > "$o/evidence/package.txt"
git -C "$k" rev-parse HEAD > "$o/kernel-base.commit"
git -C "$k" diff --binary HEAD > "$o/kernel-changes.patch"
cd "$o"
sha256sum boot.img Image kernel.config "linux-image-$release.deb" > SHA256SUMS
cat SHA256SUMS
