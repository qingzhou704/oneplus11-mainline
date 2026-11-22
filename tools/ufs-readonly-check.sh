#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read-only UFS check for the RAM shell: mark every SCSI disk read-only, then compare GPT head/tail
# regions and whole partitions against expected SHA-256 lists. Never mounts or writes storage.
# usage: ufs-readonly-check.sh GPT_LIST PART_LIST
#   GPT_LIST lines:  <disk> <offset_bytes> <length_bytes> <sha256>
#   PART_LIST lines: <partname> <length_bytes> <sha256>
gpt_list=${1:?gpt list} part_list=${2:?partition list}
for b in /sys/class/block/sd*; do blockdev --setro "/dev/${b##*/}"; done
echo "ro_flags: $(cat /sys/block/sd*/ro | tr '\n' ' ')"
for d in /sys/block/sd*; do echo "disk ${d##*/} bytes=$(( $(cat "$d/size") * 512 ))"; done
for p in /sys/class/block/sd*[0-9]*; do
    n=$(sed -n 's/^PARTNAME=//p' "$p/uevent")
    [ -n "$n" ] && echo "$n ${p##*/}"
done > /run/partmap
echo "partitions_named: $(wc -l < /run/partmap)"
while read -r disk off len sha; do
    got=$(dd if="/dev/$disk" bs=4096 skip=$((off / 4096)) count=$((len / 4096)) 2>/dev/null | sha256sum | cut -c1-64)
    [ "$got" = "$sha" ] && r=MATCH || r="DIFF $got"
    echo "gpt $disk @$off $r"
done < "$gpt_list"
while read -r name len sha; do
    dev=$(awk -v n="$name" '$1 == n { print $2 }' /run/partmap)
    if [ -z "$dev" ]; then echo "part $name MISSING"; continue; fi
    size=$(( $(cat "/sys/class/block/$dev/size") * 512 ))
    got=$(head -c "$len" "/dev/$dev" | sha256sum | cut -c1-64)
    [ "$got" = "$sha" ] && r=MATCH || r="DIFF $got"
    echo "part $name $dev size=$size $r"
done < "$part_list"
echo "ro_flags_after: $(cat /sys/block/sd*/ro | tr '\n' ' ')"
