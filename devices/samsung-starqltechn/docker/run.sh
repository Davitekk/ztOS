#!/bin/bash
# Run a build command for the Galaxy S9 (Snapdragon) port inside Docker, on a
# computer that is not Linux (Windows: from Git Bash; macOS) or not Arch.
#
#   devices/samsung-starqltechn/docker/run.sh <command...>
#   devices/samsung-starqltechn/docker/run.sh devices/samsung-starqltechn/kernel/build-kernel.sh
#   devices/samsung-starqltechn/docker/run.sh installer/ztos build --target starqltechn
#   devices/samsung-starqltechn/docker/run.sh --export out/ztos-starqltechn-boot.img
#
# The repository is copied into a Docker volume (ztos-starqltechn-build) and
# built there: a Windows or macOS filesystem keeps neither the file owners nor
# the special files an Arch Linux root is made of. --export copies a built file
# back into this checkout. aarch64 programs run through qemu-user, registered
# with the Docker VM's kernel here (it lasts until Docker restarts).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
IMAGE=ztos-starq-builder
VOLUME=ztos-starqltechn-build
export MSYS_NO_PATHCONV=1           # Git Bash: leave container paths alone

if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
	docker build -t "$IMAGE" "$HERE"
fi

# Windows paths for docker -v, from Git Bash
host_root=$ROOT
if command -v cygpath > /dev/null; then
	host_root=$(cygpath -w "$ROOT")
fi

if [ "${1:-}" = --export ]; then
	shift
	for f in "$@"; do
		mkdir -p "$ROOT/$(dirname "$f")"
		docker run --rm -v "$VOLUME:/build" -v "$host_root:/host" "$IMAGE" \
			cp "/build/ztOS/$f" "/host/$f"
		echo "exported $f"
	done
	exit 0
fi

docker run --rm --privileged "$IMAGE" sh -c '
	mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
	[ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] && exit 0
	line=$(grep -h "^:qemu-aarch64:" /usr/lib/binfmt.d/qemu-aarch64-static.conf)
	echo "$line" > /proc/sys/fs/binfmt_misc/register'

# The build tree (build/, out/) stays in the volume between runs. A Windows
# checkout shows every file as 0777 and keeps symlinks as text files, so the
# modes and links come from git's index (staged new files included), the
# contents from the working tree.
docker run --rm -i --privileged -v "$VOLUME:/build" -v "$host_root:/host:ro" "$IMAGE" bash -c '
	set -e
	mkdir -p /build/ztOS
	rsync -rlt --delete --chmod=D755,F644 --exclude=/build/ --exclude=/out/ --exclude=/.git/ /host/ /build/ztOS/
	git -c safe.directory="*" --git-dir=/host/.git --work-tree=/host ls-files -s -z |
	while IFS= read -r -d "" entry; do
		meta=${entry%%$'"'"'\t'"'"'*}; path=${entry#*$'"'"'\t'"'"'}
		mode=${meta%% *}
		case $mode in
		100755) [ -f "/build/ztOS/$path" ] && chmod 755 "/build/ztOS/$path" ;;
		120000) sha=${meta#* }; sha=${sha%% *}       # a link'"'"'s blob is its target
			target=$(git -c safe.directory="*" --git-dir=/host/.git cat-file blob "$sha")
			rm -f "/build/ztOS/$path"; ln -s "$target" "/build/ztOS/$path" ;;
		esac
	done
'

# As root in the container: the installer then builds in a plain mount
# namespace (unshare --mount), as it does for root on any host. As an
# ordinary user it would map IDs with newuidmap, whose file capabilities do
# not survive Docker's storage.
tty=
[ -t 0 ] && [ -t 1 ] && tty=-t
# (binfmt_misc is mounted per container: the installer checks for qemu-aarch64 there)
docker run --rm -i $tty --privileged -v "$VOLUME:/build" -w /build/ztOS "$IMAGE" sh -c '
	mountpoint -q /proc/sys/fs/binfmt_misc || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
	exec "$@"' sh "$@"
