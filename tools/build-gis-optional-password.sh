#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Run inside an isolated native ARM64 (or binfmt) build environment. SOURCE
# must be pristine Ubuntu 50.0-0ubuntu7.1, with distro patches already applied.
set -eu
[ "$#" -eq 2 ] || { echo 'usage: build-gis-optional-password.sh SOURCE PATCH' >&2; exit 2; }
src=$(realpath -e "$1")
patchfile=$(realpath -e "$2")
cd "$src"
[ "$(dpkg-parsechangelog -S Version)" = 50.0-0ubuntu7.1 ] || {
    echo 'expected pristine Ubuntu 50.0-0ubuntu7.1 source' >&2; exit 1;
}
patch --dry-run -p1 < "$patchfile"
patch -p1 < "$patchfile"
dpkg-checkbuilddeps
DEB_BUILD_OPTIONS="parallel=4 nocheck" dpkg-buildpackage -b -uc -us
# Debian upstream test target tolerates failures; use project regression tests
# and real AccountsService/GDM integration checks before claiming acceptance.
