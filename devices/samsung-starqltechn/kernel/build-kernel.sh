#!/bin/bash
# The Galaxy S9 (Snapdragon: SCV38, SM-G9600; starqltechn) kernel: the
# sdm845-mainline tree postmarketOS ships for this phone, postmarketOS's
# config with ztOS's additions (ztos.config), brcmfmac for the BCM4361 and the
# device tree edits of patch-dts.py.
#
#   devices/samsung-starqltechn/kernel/build-kernel.sh [-j N]
#
# Out: build/linux-<tag>/out/{arch/arm64/boot/Image.gz, the dtb, modroot/}.
# Runs on any Linux with clang, lld and llvm (LLVM=1 cross-compiles to arm64
# without a separate toolchain); nothing needs root.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
TAG=sdm845-7.1-rc1-r0
# the tarball postmarketOS's linux-postmarketos-qcom-sdm845 7.1_rc1 builds from
SHA512=94da173aaf74dd33ef8ff9015e92759481cd0da5bd8a1e52c8664fd372d48a1155655001ad2e9d26557733c71ae8bc448e4ebdf1372b8f32159907a35f0306a9
URL=https://gitlab.com/sdm845-mainline/linux/-/archive/$TAG/linux-$TAG.tar.gz
DTB=qcom/sdm845-samsung-starqltechn.dtb

JOBS=$(nproc)
[ "${1:-}" = -j ] && JOBS=$2

B=$ROOT/build/linux-$TAG
SRC=$B/src
OUT=$B/out
TARBALL=$ROOT/build/linux-$TAG.tar.gz
mkdir -p "$ROOT/build"

if [ ! -f "$TARBALL" ] || ! echo "$SHA512  $TARBALL" | sha512sum -c --status; then
	echo "kernel: downloading $URL"
	curl -L --fail -o "$TARBALL.part" "$URL"
	echo "$SHA512  $TARBALL.part" | sha512sum -c --quiet
	mv "$TARBALL.part" "$TARBALL"
fi

# A fresh tree on every build: the patches assert their anchors, and a tree
# left half patched by an earlier run must not pass them.
echo "kernel: unpacking $TAG"
rm -rf "$SRC"
mkdir -p "$SRC"
tar -xzf "$TARBALL" -C "$SRC" --strip-components=1

python3 "$HERE/patch-brcmfmac-4361.py" "$SRC"
python3 "$HERE/patch-btbcm.py" "$SRC"
python3 "$HERE/patch-muic.py" "$SRC"
python3 "$HERE/patch-panel-backlight.py" "$SRC"
python3 "$HERE/patch-dts.py" "$SRC"

mkdir -p "$OUT"
cp "$HERE/config-sdm845.aarch64" "$OUT/.config"
M=(make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 KBUILD_BUILD_USER=ztos KBUILD_BUILD_HOST=ztos)
# With ccache a rebuild takes minutes: the tree is unpacked afresh each time,
# at the same path, so everything a patch did not touch is a cache hit.
if command -v ccache > /dev/null; then
	export CCACHE_DIR=$ROOT/build/ccache CCACHE_BASEDIR=$B CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime
	M+=(CC="ccache clang" HOSTCC="ccache clang")
fi
"$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" "$OUT/.config" "$HERE/ztos.config" > /dev/null
"${M[@]}" olddefconfig > /dev/null

# Every line of ztos.config must have survived olddefconfig: a "=y" that
# Kconfig quietly made "=m" (a dependency still modular) would leave the
# screen dark until the root is mounted.
bad=0
while IFS= read -r line; do
	case "$line" in
	CONFIG_*=*) grep -qxF "$line" "$OUT/.config" || { echo "kernel: config lost: $line" >&2; bad=1; } ;;
	"# CONFIG_"*" is not set")
		sym=${line#\# }; sym=${sym%% *}
		grep -q "^$sym=" "$OUT/.config" && { echo "kernel: config should be off: $sym" >&2; bad=1; } ;;
	esac
done < "$HERE/ztos.config"
[ "$bad" = 0 ] || exit 1

echo "kernel: building with $JOBS jobs"
"${M[@]}" -j"$JOBS" Image.gz dtbs modules
rm -rf "$OUT/modroot"
"${M[@]}" INSTALL_MOD_PATH="$OUT/modroot" INSTALL_MOD_STRIP=1 modules_install > /dev/null
KREL=$(cat "$OUT/include/config/kernel.release")
rm -f "$OUT/modroot/lib/modules/$KREL/build" "$OUT/modroot/lib/modules/$KREL/source"
echo "$KREL" > "$OUT/kernel.release"
ls -l "$OUT/arch/arm64/boot/Image.gz" "$OUT/arch/arm64/boot/dts/$DTB"
echo "kernel: $KREL ready"
