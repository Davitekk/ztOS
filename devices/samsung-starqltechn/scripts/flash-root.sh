#!/bin/bash
# Write ztOS's root image into USERDATA of the Galaxy S9 (Snapdragon) from its
# running TWRP, in verified chunks.
#
#   devices/samsung-starqltechn/scripts/flash-root.sh <root.img> [chunk MiB]
#   devices/samsung-starqltechn/scripts/flash-root.sh <chunk directory>     (root-chunks.sh's)
#
# EVERYTHING IN USERDATA IS ERASED: Android's data and the phone's storage.
# Each chunk is compared with the partition first and only sent when it
# differs, then read back and compared again, so a run cut short (a cable
# pulled) is finished by running it again. Nothing but USERDATA is written.
# Runs on Linux, macOS and Git Bash on Windows.
set -euo pipefail
export MSYS_NO_PATHCONV=1
IMG=${1:?root image or chunk directory}
CHUNK=${2:-256}
NODE=/dev/block/sda28
BY=/dev/block/platform/soc/1d84000.ufshc/by-name/userdata
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

sh() { adb shell "$@" | tr -d '\r'; }
# a local path as adb itself takes it (a Windows one from Git Bash)
local_path() { if command -v cygpath > /dev/null; then cygpath -w "$1"; else echo "$1"; fi; }

[ "$(adb get-state 2>/dev/null)" = recovery ] || { echo "the phone is not in TWRP" >&2; exit 1; }
[ "$(sh getprop ro.product.device)" = starqltechn ] || { echo "not a starqltechn TWRP" >&2; exit 1; }
[ "$(sh readlink -f "$BY")" = "$NODE" ] || { echo "USERDATA is not $NODE on this phone" >&2; exit 1; }

if [ -d "$IMG" ]; then
	# root-chunks.sh's pieces: gzip chunks and the sha256 of each as in the image
	[ -f "$IMG/info" ] && [ -f "$IMG/SHA256SUMS" ] || { echo "$IMG: no info or SHA256SUMS (root-chunks.sh)" >&2; exit 1; }
	SIZE=$(sed -n 's/^size=//p' "$IMG/info")
	CHUNK=$(sed -n 's/^chunk=//p' "$IMG/info")
	magic=$(gzip -dc "$IMG/0000.gz" | od -An -tx2 -j 1080 -N 2 | tr -d ' ')
else
	[ -s "$IMG" ] || { echo "no image: $IMG" >&2; exit 1; }
	SIZE=$(wc -c < "$IMG" | tr -d ' ')
	magic=$(od -An -tx2 -j 1080 -N 2 "$IMG" | tr -d ' ')
fi
[ "$magic" = ef53 ] || { echo "$IMG is not an ext4 image" >&2; exit 1; }
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
	name=$(printf '%04d' "$i")
	if [ -d "$IMG" ]; then
		want=$(sed -n "s/^\([0-9a-f]\{64\}\)  $name\$/\1/p" "$IMG/SHA256SUMS")
		[ -n "$want" ] || { echo "$IMG/SHA256SUMS has no chunk $name" >&2; exit 1; }
		gz=$IMG/$name.gz
	else
		want=$(dd if="$IMG" bs=1048576 skip="$off" count="$CHUNK" status=none | sha256sum | cut -d' ' -f1)
		gz=$TMP/chunk.gz
	fi
	if [ "$(part_hash "$i")" = "$want" ]; then
		skipped=$((skipped + 1))
		printf '%3d/%d  identical, skipped\n' "$((i + 1))" "$N"
		continue
	fi
	[ -d "$IMG" ] || dd if="$IMG" bs=1048576 skip="$off" count="$CHUNK" status=none | gzip -1 > "$gz"
	ok=
	for try in 1 2 3; do
		adb push "$(local_path "$gz")" /tmp/ztos-chunk.gz > /dev/null
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
