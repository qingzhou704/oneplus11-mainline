#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Offline check for import-modem-data: the GPU import already created the shared firmware
# directory, and two boots must both succeed.   usage: sh tests/import-modem-data.sh
set -eu
src=$(cd "$(dirname "$0")/.." && pwd)/rootfs/salami-device/usr/lib/salami/import-modem-data
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/parts" "$T/img/image/modem_pr" "$T/fw/qcom/sm8550/oneplus/salami"
mkdir -p "$T/rproc/remoteproc0" "$T/rproc/remoteproc1"
touch "$T/fw/qcom/sm8550/oneplus/salami/a740_zap.mbn"
for f in adsp.mdt adsp.b00 modem.mdt ipa_fws.mdt x.jsn modem_pr/a.txt cdsp.mdt cdsp_dtb.mdt cdsp.b00; do
    echo "$f" > "$T/img/image/$f"
done
for p in modemst1 modemst2 fsg fsc oplusstanvbk_a oplusdycnvbk; do echo "$p" > "$T/parts/$p"; done
printf '%s\n' "qcom/sm8550/oneplus/salami/adsp.mdt" > "$T/rproc/remoteproc0/firmware"
printf '%s\n' "offline" > "$T/rproc/remoteproc0/state"
printf '%s\n' "qcom/sm8550/oneplus/salami/cdsp.mdt" > "$T/rproc/remoteproc1/firmware"
printf '%s\n' "offline" > "$T/rproc/remoteproc1/state"
printf '#!/bin/sh\necho mount >> "%s/mounts"\ncp -r "%s/img/." "$4"\n' "$T" "$T" > "$T/bin/mount"
printf '#!/bin/sh\nfind "$1" -mindepth 1 -delete\n' > "$T/bin/umount"
chmod +x "$T/bin/"*
sed -e "s|/usr/lib/firmware|$T/fw|" -e "s|/var/lib/rmtfs|$T/efs|" \
    -e "s|/dev/disk/by-partlabel|$T/parts|g" -e "s|/sys/class/remoteproc|$T/rproc|g" \
    "$src" > "$T/run.sh"
for boot in 1 2; do PATH="$T/bin:$PATH" sh "$T/run.sh"; done
d=$T/fw/qcom/sm8550/oneplus/salami
for f in a740_zap.mbn adsp.mdt adsp.b00 modem.mdt ipa_fws.mdt x.jsn modem_pr/a.txt cdsp.mdt cdsp_dtb.mdt cdsp.b00; do
    test -f "$d/$f"
done
test ! -e "$d.tmp"; test ! -e "$d/salami.tmp"
test -f "$T/efs/modem_fs1"; test -f "$T/efs/oem_dycnvbk"
test "$(wc -l < "$T/mounts")" -eq 1
test "$(cat "$T/rproc/remoteproc0/state")" = start
test "$(cat "$T/rproc/remoteproc1/state")" = start

# Upgrade path: pre-0.30 host already has adsp.mdt and EFS, but lacks cdsp*.
rm -f "$T/mounts" "$d/cdsp.mdt" "$d/cdsp_dtb.mdt" "$d/cdsp.b00"
printf '%s\n' "EXISTING_ADSP" > "$d/adsp.mdt"
printf '%s\n' "running" > "$T/rproc/remoteproc0/state"
printf '%s\n' "offline" > "$T/rproc/remoteproc1/state"
for boot in 1 2; do PATH="$T/bin:$PATH" sh "$T/run.sh"; done
test "$(cat "$d/adsp.mdt")" = "EXISTING_ADSP"
for f in a740_zap.mbn cdsp.mdt cdsp_dtb.mdt cdsp.b00; do test -f "$d/$f"; done
test "$(wc -l < "$T/mounts")" -eq 1
test "$(cat "$T/rproc/remoteproc0/state")" = running
test "$(cat "$T/rproc/remoteproc1/state")" = start
echo PASS
