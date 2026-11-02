#!/bin/bash
# A minimal aarch64 root for build-boot.sh --sysroot when no ztOS system has
# been built yet (testing the boot image alone): Arch Linux ARM's
# busybox and the libraries it runs on, each package checked
# against the repository's SHA-256 and the Arch Linux ARM build key's
# signature.
#
#   devices/microsoft-talkman/boot/alarm-sysroot.sh     -> build/alarm-sysroot
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
MIRROR=http://mirror.archlinuxarm.org/aarch64
# Arch Linux ARM Build System <builder@archlinuxarm.org>
KEY=68B3537F39A313B3E574D06777193F152BDBE6A6
W=$ROOT/build/alarm-sysroot
PKGS="extra/busybox core/glibc core/libxcrypt"

mkdir -p "$W/pkg" "$W/root"
export GNUPGHOME=$W/gnupg
mkdir -p -m 700 "$GNUPGHOME"
gpg -q --list-keys "$KEY" > /dev/null 2>&1 ||
	gpg -q --keyserver hkps://keyserver.ubuntu.com --recv-keys "$KEY"

for entry in $PKGS; do
	repo=${entry%%/*}; name=${entry#*/}
	db=$W/pkg/$repo.db
	[ -f "$db" ] || curl -sSL --fail -o "$db" "$MIRROR/$repo/$repo.db"
	# "<name>-<digit>": the package itself, not one whose name only starts with it
	desc=$(bsdtar -xOf "$db" --include "$name-[0-9]*/desc" 2>/dev/null)
	[ "$(echo "$desc" | sed -n '/^%NAME%$/{n;p}')" = "$name" ] || { echo "sysroot: $name not in $repo" >&2; exit 1; }
	file=$(echo "$desc" | sed -n '/^%FILENAME%$/{n;p}')
	sha=$(echo "$desc" | sed -n '/^%SHA256SUM%$/{n;p}')
	[ -n "$file" ] && [ -n "$sha" ] || { echo "sysroot: $name not in $repo" >&2; exit 1; }
	if [ ! -f "$W/pkg/$file" ]; then
		curl -sSL --fail -o "$W/pkg/$file" "$MIRROR/$repo/$file"
		curl -sSL --fail -o "$W/pkg/$file.sig" "$MIRROR/$repo/$file.sig"
	fi
	echo "$sha  $W/pkg/$file" | sha256sum -c --quiet
	gpg -q --verify "$W/pkg/$file.sig" "$W/pkg/$file" 2>&1 | grep -q "Good signature" ||
		gpg --status-fd 1 --verify "$W/pkg/$file.sig" "$W/pkg/$file" 2>/dev/null | grep -q "VALIDSIG $KEY" ||
		{ echo "sysroot: $file: bad or missing signature" >&2; exit 1; }
	bsdtar -xpf "$W/pkg/$file" -C "$W/root" --exclude '.*' usr
	echo "sysroot: $file"
done
echo "sysroot: $W/root"
