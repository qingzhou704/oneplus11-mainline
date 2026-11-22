#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Native arm64 build: pinned upstream source tar + Ubuntu 1.1.1-2 base deb + OUT.
# Needs gcc, make, libc6-dev, libqrtr-dev, libudev-dev, dpkg-deb and python3.
set -eu
[ "$#" -eq 3 ] || { echo "usage: $0 SOURCE_TAR BASE_DEB OUT" >&2; exit 2; }
src=$1 base=$2 out=$3
printf '%s  %s\n' \
  cfaae038a5f1f43a8f15bef2a4ec26ca047746b9d2ff64e6ab43ad3cb135a033 "$src" \
  916a98ec0f89a2ec25a121f247594ba74e93b9e047bbc30b2e2dc5605144b96c "$base" | sha256sum -c -
[ "$(dpkg --print-architecture)" = arm64 ]
[ "$(dpkg-deb -f "$base" Version)" = 1.1.1-2 ]
mkdir -p "$out"
mkdir "$out/source"
tar -xzf "$src" -C "$out/source" --strip-components=1
make -C "$out/source" -j4
dpkg-deb -R "$base" "$out/pkg"
install -m 755 "$out/source/rmtfs" "$out/pkg/usr/bin/rmtfs"
# Built natively against this system's glibc, so require at least that upstream version.
libc=$(dpkg-query -W -f '${Version}' libc6)
python3 - "$out/pkg/DEBIAN/control" "${libc%%-*}" <<'PY'
from pathlib import Path
import re, sys
p = Path(sys.argv[1])
s = p.read_text().replace('Version: 1.1.1-2\n', 'Version: 1.1.1-2+salami1\n')
s = re.sub(r'libc6 \(>= [^)]+\)', f'libc6 (>= {sys.argv[2]})', s)
p.write_text(s)
PY
install -m 644 "$out/source/LICENSE" "$out/pkg/usr/share/doc/rmtfs/LICENSE.upstream"
cat > "$out/pkg/usr/share/doc/rmtfs/salami-upstream.txt" <<'EOF'
Built from linux-msm/rmtfs commit 291e16dbd1f1c2cfc660ea7f77767571185e1a3a.
https://github.com/linux-msm/rmtfs/commit/291e16dbd1f1c2cfc660ea7f77767571185e1a3a
Adds OnePlus/Oppo OEM NV file mappings. Ubuntu packaging and service units retained.
EOF
(cd "$out/pkg"; find . -type f ! -path './DEBIAN/*' -print0 | LC_ALL=C sort -z | xargs -0 md5sum > DEBIAN/md5sums)
dpkg-deb --root-owner-group -Zxz --build "$out/pkg" "$out/rmtfs.deb"
sha256sum "$src" "$base" "$out/rmtfs.deb" > "$out/SHA256SUMS"
cat "$out/SHA256SUMS"
