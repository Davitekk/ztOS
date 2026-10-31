#!/bin/bash
# Write a boot image to BOOT of the Galaxy S9 (Snapdragon) from its running
# TWRP (official TWRP 3.7.0 for starqltechn; on the SCV38 too).
#
#   devices/samsung-starqltechn/scripts/flash.sh BOOT <image>
#   devices/samsung-starqltechn/scripts/flash.sh BOOT stock/starqltechn/boot.img    back to Android's kernel
#
# Refuses to run without the stock backups (backup.sh), checks the device and
# the partition mapping, verifies the copy on the phone before writing and the
# partition after. Never reboots. Runs on Linux, macOS and Git Bash on Windows.
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PART=${1:?BOOT}
IMG=${2:?image}
case "$PART" in
BOOT) NODE=/dev/block/sda20; NAME=boot ;;
*) echo "only BOOT (ztOS never writes anything else but USERDATA: flash-root.sh)" >&2; exit 2 ;;
esac
STOCK=$ROOT/stock/starqltechn
for f in boot efs modemst1 modemst2 fsg persist; do
	[ -s "$STOCK/$f.img" ] || { echo "stock/starqltechn/$f.img missing: run backup.sh first" >&2; exit 1; }
done
[ "$(head -c 8 "$IMG")" = "ANDROID!" ] || { echo "$IMG: not an Android boot image" >&2; exit 1; }
BY=/dev/block/platform/soc/1d84000.ufshc/by-name/$NAME
sh() { adb shell "$@" | tr -d '\r'; }
[ "$(adb get-state 2>/dev/null)" = recovery ] || { echo "the phone is not in TWRP (adb get-state: $(adb get-state 2>&1))" >&2; exit 1; }
[ "$(sh getprop ro.product.device)" = starqltechn ] || { echo "not a starqltechn TWRP" >&2; exit 1; }
[ "$(sh readlink -f "$BY")" = "$NODE" ] || { echo "$PART is not $NODE on this phone" >&2; exit 1; }
SIZE=$(wc -c < "$IMG" | tr -d ' ')
[ "$SIZE" -le "$(sh blockdev --getsize64 "$BY")" ] || { echo "image does not fit $PART" >&2; exit 1; }
SUM=$(sha256sum "$IMG" | cut -d' ' -f1)
adb push "$IMG" /tmp/zboot-flash.img > /dev/null
[ "$(sh sha256sum /tmp/zboot-flash.img | cut -d' ' -f1)" = "$SUM" ] || { echo "USB copy mismatch" >&2; exit 1; }
sh "dd if=/tmp/zboot-flash.img of=$BY bs=1048576 2>/dev/null && sync"
BACK=$(sh "head -c $SIZE $BY | sha256sum" | cut -d' ' -f1)
sh rm -f /tmp/zboot-flash.img
[ "$BACK" = "$SUM" ] || { echo "READBACK MISMATCH on $PART: write the stock image back (stock/starqltechn/boot.img)" >&2; exit 1; }
echo "FLASHED $PART <- $(basename "$IMG") sha256=$SUM bytes=$SIZE (readback verified)"
