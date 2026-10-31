#!/bin/bash
# Save what cannot be had back from Samsung's firmware, from the phone's
# running TWRP: its identity and calibration (EFS: IMEI, Wi-Fi and Bluetooth
# addresses; modemst1/2, fsg, fsc: the modem's own copy; persist: sensor
# calibration), param, sec, and the stock BOOT, DTBO and VBMETA to go back.
#
#   devices/samsung-starqltechn/scripts/backup.sh       -> stock/starqltechn/*.img, SHA256SUMS
#
# Each partition is read twice, on the phone (sha256sum) and through adb, and
# kept only when both agree. Never writes to the phone. Done once: a partition
# already saved is left alone.
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
OUT=$ROOT/stock/starqltechn
BN=/dev/block/platform/soc/1d84000.ufshc/by-name
PARTS="efs modemst1 modemst2 fsg fsc persist param sec boot dtbo vbmeta"

sh() { adb shell "$@" | tr -d '\r'; }
[ "$(adb get-state 2>/dev/null)" = recovery ] || { echo "the phone is not in TWRP" >&2; exit 1; }
[ "$(sh getprop ro.product.device)" = starqltechn ] || { echo "not a starqltechn TWRP" >&2; exit 1; }
mkdir -p "$OUT"
for p in $PARTS; do
	if [ -s "$OUT/$p.img" ] && grep -q " $p.img\$" "$OUT/SHA256SUMS" 2>/dev/null; then
		echo "kept  $p (already saved)"
		continue
	fi
	dev=$(sh readlink -f "$BN/$p")
	case $dev in /dev/block/sd*) ;; *) echo "no $p partition ($dev)" >&2; exit 1 ;; esac
	want=$(sh "sha256sum $dev" | cut -d' ' -f1)
	adb exec-out "cat $dev" > "$OUT/$p.img.part"
	have=$(sha256sum "$OUT/$p.img.part" | cut -d' ' -f1)
	[ -n "$want" ] && [ "$want" = "$have" ] || { rm -f "$OUT/$p.img.part"; echo "$p: copy does not match the phone" >&2; exit 1; }
	mv "$OUT/$p.img.part" "$OUT/$p.img"
	sed -i "/ $p.img\$/d" "$OUT/SHA256SUMS" 2>/dev/null || true
	echo "$have  $p.img" >> "$OUT/SHA256SUMS"
	echo "saved $p ($dev, $(wc -c < "$OUT/$p.img" | tr -d ' ') bytes)"
done
echo "stock/starqltechn: everything saved and checked. Keep a copy of it somewhere else too."
