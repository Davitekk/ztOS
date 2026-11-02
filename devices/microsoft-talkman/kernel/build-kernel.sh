#!/bin/bash
# The Lumia 950 (talkman, MSM8992) kernel: Android4Lumia950's mainline tree,
# its mmo_defconfig with ztOS's additions (ztos.config).
#
#   devices/microsoft-talkman/kernel/build-kernel.sh [-j N]
#
# Out: build/linux-talkman/out/{arch/arm64/boot/Image.gz, the dtb, modroot/}.
# Runs on any Linux with clang, lld and llvm (LLVM=1 cross-compiles to arm64
# without a separate toolchain); nothing needs root.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
URL=https://github.com/Android4Lumia950/linux.git
COMMIT=eb871dc826f40143a644e782148adae3fb08f331
DTB=qcom/msm8992-msft-lumia-octagon-talkman.dtb

JOBS=${ZTOS_BUILD_CPUS:-$(nproc)}
[ "${1:-}" = -j ] && JOBS=$2

B=$ROOT/build/linux-talkman
GIT=$B/git
SRC=$B/src
OUT=$B/out
mkdir -p "$B"

# The commit's hash vouches for the source
if ! git -C "$GIT" cat-file -e "$COMMIT^{commit}" 2> /dev/null; then
	echo "kernel: fetching $COMMIT"
	git init -q --bare "$GIT"
	git -C "$GIT" fetch -q --depth 1 "$URL" "$COMMIT"
fi

# A fresh tree on every build: the patches assert their anchors, and a tree
# left half patched by an earlier run must not pass them. Every file is dated
# now (git archive would date them all at the commit), so that make never keeps
# an object built from a source a patch has since left; ccache keeps the full
# rebuild this means quick.
echo "kernel: unpacking $COMMIT"
rm -rf "$SRC"
mkdir -p "$SRC"
git -C "$GIT" archive "$COMMIT" | tar -x -C "$SRC" --touch

python3 "$HERE/patch-dts.py" "$SRC"
python3 "$HERE/patch-dsi-cfg.py" "$SRC"
python3 "$HERE/patch-pon-reset.py" "$SRC"
python3 "$HERE/patch-mdp5-cfg.py" "$SRC"
python3 "$HERE/patch-mmcc-gpu.py" "$SRC"
python3 "$HERE/patch-gpu-a418.py" "$SRC"

mkdir -p "$OUT"
M=(make -C "$SRC" O="$OUT" ARCH=arm64 LLVM=1 KBUILD_BUILD_USER=ztos KBUILD_BUILD_HOST=ztos)
# With ccache a rebuild takes minutes: the tree is unpacked afresh each time,
# at the same path, so everything a patch did not touch is a cache hit.
if command -v ccache > /dev/null; then
	export CCACHE_DIR=$ROOT/build/ccache CCACHE_BASEDIR=$B CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime
	M+=(CC="ccache clang" HOSTCC="ccache clang")
fi
"${M[@]}" mmo_defconfig > /dev/null
"$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" "$OUT/.config" "$HERE/ztos.config" > /dev/null
"${M[@]}" olddefconfig > /dev/null

# Every line of ztos.config must have survived olddefconfig: a "=y" that
# Kconfig quietly dropped (a dependency missing) would only show on the phone.
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
