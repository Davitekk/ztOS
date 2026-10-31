#!/bin/sh
# Cut ztOS's root image into the gzip pieces flash-root.sh writes, so it can
# be carried out of a build host (Docker on Windows: devices/.../docker/run.sh
# --export) at the size of what is in it, not 10 GB.
#
#   devices/samsung-starqltechn/scripts/root-chunks.sh <root.img> <dir> [chunk MiB]
#
# <dir>/NNNN.gz, one per chunk; <dir>/SHA256SUMS, the sha256 of each chunk as
# it is in the image (what flash-root.sh compares the partition with);
# <dir>/info, the image's size and the chunk size.
set -eu
img=${1:?root image}
dir=${2:?directory}
chunk=${3:-256}
size=$(stat -c %s "$img")
bytes=$((chunk * 1048576))
[ $((size % bytes)) -eq 0 ] || { echo "image size is not a multiple of $chunk MiB" >&2; exit 1; }
n=$((size / bytes))
rm -rf "$dir"
mkdir -p "$dir"
i=0
while [ "$i" -lt "$n" ]; do
	name=$(printf '%04d' "$i")
	dd if="$img" bs=1048576 skip=$((i * chunk)) count="$chunk" status=none | tee "$dir/$name.raw" |
		sha256sum | sed "s/ .*/  $name/" >> "$dir/SHA256SUMS"
	gzip -1 -c "$dir/$name.raw" > "$dir/$name.gz"
	rm "$dir/$name.raw"
	i=$((i + 1))
done
printf 'size=%s\nchunk=%s\n' "$size" "$chunk" > "$dir/info"
echo "root-chunks: $n chunks of $chunk MiB in $dir ($(du -sh "$dir" | cut -f1))"
