#!/bin/bash
# Write ztOS's root image into USERDATA of the Galaxy S9 (Snapdragon) from its
# running TWRP, in verified chunks.
#
#   devices/samsung-starqltechn/scripts/flash-root.sh <root.img> [chunk MiB]
#
# EVERYTHING IN USERDATA IS ERASED: Android's data and the phone's storage.
# Each chunk is compared with the partition first and only sent when it
# differs, then read back and compared again, so a run cut short (a cable
# pulled) is finished by running it again. Nothing but USERDATA is written.
# Runs on Linux, macOS and Git Bash on Windows.
set -euo pipefail
export MSYS_NO_PATHCONV=1
IMG=${1:?root image}
CHUNK=${2:-256}
NODE=/dev/block/sda28
BY=/dev/block/platform/soc/1d84000.ufshc/by-name/userdata
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

sh() { adb shell "$@" | tr -d '\r'; }
[ "$(adb get-state 2>/dev/null)" = recovery ] || { echo "the phone is not in TWRP" >&2; exit 1; }
[ "$(sh getprop ro.product.device)" = starqltechn ] || { echo "not a starqltechn TWRP" >&2; exit 1; }
[ "$(sh readlink -f "$BY")" = "$NODE" ] || { echo "USERDATA is not $NODE on this phone" >&2; exit 1; }
[ -s "$IMG" ] || { echo "no image: $IMG" >&2; exit 1; }
[ "$(od -An -tx2 -j 1080 -N 2 "$IMG" | tr -d ' ')" = ef53 ] || { echo "$IMG is not an ext4 image" >&2; exit 1; }
SIZE=$(wc -c < "$IMG" | tr -d ' ')
BYTES=$((CHUNK * 1048576))
(( SIZE % BYTES == 0 )) || { echo "image size is not a multiple of ${CHUNK} MiB" >&2; exit 1; }
N=$((SIZE / BYTES))
PSIZE=$(sh blockdev --getsize64 "$BY")
[ "$PSIZE" -ge $((SIZE + 1048576)) ] || { echo "USERDATA ($PSIZE bytes) is too small for $SIZE" >&2; exit 1; }
echo "image $IMG: $SIZE bytes, $N chunks of $CHUNK MiB -> USERDATA ($NODE, $PSIZE bytes)"

# TWRP must not have USERDATA mounted while it is written
sh "umount /data 2>/dev/null; umount /sdcard 2>/dev/null; grep -q '^$NODE ' /proc/mounts && echo mounted || true" |
	grep -q mounted && { echo "USERDATA is still mounted in TWRP: unmount Data under Mount, then run this again" >&2; exit 1; }

part_hash() {   # sha256 of chunk $1 as the phone reads it
	sh "dd if=$BY bs=1048576 skip=$(($1 * CHUNK)) count=$CHUNK 2>/dev/null | sha256sum" | cut -d' ' -f1
}

sent=0 skipped=0
for ((i = 0; i < N; i++)); do
	off=$((i * CHUNK))
	want=$(dd if="$IMG" bs=1048576 skip="$off" count="$CHUNK" status=none | sha256sum | cut -d' ' -f1)
	if [ "$(part_hash "$i")" = "$want" ]; then
		skipped=$((skipped + 1))
		printf '%3d/%d  identical, skipped\n' "$((i + 1))" "$N"
		continue
	fi
	dd if="$IMG" bs=1048576 skip="$off" count="$CHUNK" status=none | gzip -1 > "$TMP/chunk.gz"
	ok=
	for try in 1 2 3; do
		adb push "$TMP/chunk.gz" /tmp/ztos-chunk.gz > /dev/null
		# a pipe gives dd short reads, so no count=: the chunk's own length
		# ends the write; seek= puts it at the chunk's offset
		sh "gunzip -c /tmp/ztos-chunk.gz | dd of=$BY bs=1048576 seek=$off conv=notrunc 2>/dev/null; sync; rm -f /tmp/ztos-chunk.gz"
		if [ "$(part_hash "$i")" = "$want" ]; then ok=1; break; fi
		echo "   chunk $((i + 1)) read back different (try $try)" >&2
	done
	[ -n "$ok" ] || { echo "chunk $((i + 1)) failed three times: stopping (run again to carry on)" >&2; exit 1; }
	sent=$((sent + 1))
	printf '%3d/%d  written and verified\n' "$((i + 1))" "$N"
done
echo "FLASH_ROOT_OK $sent chunk(s) written, $skipped already identical"
