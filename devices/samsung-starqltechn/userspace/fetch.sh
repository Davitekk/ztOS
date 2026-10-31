#!/bin/sh
# Download userspace/sources.txt into <dir>, each checked against its sha512;
# a file already there and matching is not downloaded again. Runs on the
# build host (layer.sh calls it before building them in the phone's root).
#
#   devices/samsung-starqltechn/userspace/fetch.sh <dir>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dir=${1:?directory}
mkdir -p "$dir"
grep -v '^#' "$here/sources.txt" | while read -r name url sum; do
	[ -n "$name" ] || continue
	if [ -f "$dir/$name" ] && echo "$sum  $dir/$name" | sha512sum -c --status; then
		continue
	fi
	curl -sSL --fail -o "$dir/$name.part" "$url"
	echo "$sum  $dir/$name.part" | sha512sum -c --quiet ||
		{ rm -f "$dir/$name.part"; echo "fetch: $name does not match its sha512" >&2; exit 1; }
	mv "$dir/$name.part" "$dir/$name"
	echo "fetch: $name"
done
