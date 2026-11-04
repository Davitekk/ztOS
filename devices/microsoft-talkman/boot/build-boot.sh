#!/bin/bash
# The Lumia 950's boot image, for fastboot boot or its boot partition.
#
#   devices/microsoft-talkman/boot/build-boot.sh --sysroot <aarch64 root> [--cmdline "..."] [--name N] [--firmware <dir>]
#
# The boot stage's busybox is the busybox package's (usr/bin/busybox) from the
# aarch64 root given, the ztOS system being built or boot/alarm-sysroot.sh's:
# on Arch Linux ARM it is dynamically linked, so its libraries come from the
# same root.
#
# The chain: the phone's UEFI starts BootShim and LK (lk2nd), which loads an
# Android boot image (header v0) whose kernel is Image.gz with the device tree
# appended; LK takes the tree by its qcom,msm-id, board-id and pmic-id
# (kernel/patch-dts.py).
#
# Needs: build-kernel.sh run first; mkbootimg (android-tools), cpio. Out:
# out/<name>.img.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DEV=$(dirname "$HERE")
ROOT=$(cd "$DEV/../.." && pwd)
KOUT=$ROOT/build/linux-talkman/out
DTB=$KOUT/arch/arm64/boot/dts/qcom/msm8992-msft-lumia-octagon-talkman.dtb

# LK's addresses for this phone (lk2nd, project/msm8994.mk: ABOOT_FORCE_*), which
# it uses whatever the header says: the same here, so that they hold either way
KERNEL_ADDR=0x00080000
TAGS_ADDR=0x02500000
RAMDISK_ADDR=0x02700000
# the device tree's first reservation after them is cont_splash_mem
RAMDISK_END=0x03400000

NAME=ztos-talkman-boot
SYSROOT=
FIRMWARE=
# driver_async_probe: the fuel gauge's probe takes 20 s and the light sensor's times
# out in 6 s; started in the background, the kernel is up in 2 s rather than 26 s
CMDLINE="console=tty0 loglevel=3 quiet panic=5 cma=256M driver_async_probe=qcom-pmi8994-fg,tsl2772"
while [ $# -gt 0 ]; do
	case $1 in
	--sysroot) SYSROOT=$2; shift ;;
	--cmdline) CMDLINE="$CMDLINE $2"; shift ;;
	--name) NAME=$2; shift ;;
	--firmware) FIRMWARE=$2; shift ;;
	*) echo "unknown option $1" >&2; exit 2 ;;
	esac
	shift
done
BUSYBOX=$SYSROOT/usr/bin/busybox
[ -n "$SYSROOT" ] && [ -f "$BUSYBOX" ] || { echo "boot: --sysroot <aarch64 root with the busybox package> is needed" >&2; exit 2; }
file -L "$BUSYBOX" | grep -q "ARM aarch64" || { echo "boot: $BUSYBOX is not an aarch64 program" >&2; exit 1; }
for f in "$KOUT/arch/arm64/boot/Image" "$KOUT/arch/arm64/boot/Image.gz" "$DTB" "$KOUT/kernel.release"; do
	[ -f "$f" ] || { echo "boot: no $f: run devices/microsoft-talkman/kernel/build-kernel.sh first" >&2; exit 1; }
done
fdtget -t x "$DTB" / qcom,board-id > /dev/null || { echo "boot: $DTB has no qcom,board-id: LK would not take it" >&2; exit 1; }

W=$ROOT/build/talkman-boot
mkdir -p "$W" "$ROOT/out"

# --- the boot stage (initramfs) --------------------------------------------------
I=$W/initramfs
rm -rf "$I"
# Arch's layout: glibc's loader searches /usr/lib only, and /lib is a link to it
mkdir -p "$I"/{bin,sbin,dev,proc,sys,run,tmp,newroot,etc,usr/lib,usr/bin,usr/sbin}
ln -s usr/lib "$I/lib"
install -m755 "$BUSYBOX" "$I/bin/busybox"
# /init is a shell script: the kernel runs its #!/bin/sh before busybox has
# made any of its other links
ln -s busybox "$I/bin/sh"
# its libraries, and theirs, from the same root (the loader is one of them)
deps() {
	local lib
	for lib in $(readelf -d "$1" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p'); do
		[ -e "$I/usr/lib/$lib" ] && continue
		[ -e "$SYSROOT/usr/lib/$lib" ] || { echo "boot: $lib (for $(basename "$1")) not in $SYSROOT/usr/lib" >&2; exit 1; }
		cp -L "$SYSROOT/usr/lib/$lib" "$I/usr/lib/$lib"
		chmod 755 "$I/usr/lib/$lib"
		deps "$I/usr/lib/$lib"
	done
}
deps "$I/bin/busybox"
interp=$(readelf -l "$I/bin/busybox" | sed -n 's/.*interpreter: \(.*\)\]/\1/p')
# (none at all for a static busybox, as Arch Linux ARM's busybox package is)
[ -z "$interp" ] || { [ "$interp" = /lib/ld-linux-aarch64.so.1 ] && [ -e "$I/usr/lib/${interp#/lib/}" ]; } ||
	{ echo "boot: busybox's loader ($interp) missing" >&2; exit 1; }
install -m755 "$DEV/initramfs/init" "$I/init"
# for a boot image with no root behind it: the drivers built into the kernel
# find their firmware here
if [ -n "$FIRMWARE" ]; then
	mkdir -p "$I/usr/lib/firmware"
	cp -a "$FIRMWARE/." "$I/usr/lib/firmware/"
fi
# Run it before it goes anywhere near the phone: the shell that /init names
# must start in this tree, as the kernel will start it (aarch64 through
# qemu-user's binfmt handler on an x86 host; needs root for chroot).
SUDO=
[ "$(id -u)" = 0 ] || SUDO="sudo -n"
if [ -z "$SUDO" ] || sudo -n true 2> /dev/null; then
	out=$($SUDO chroot "$I" /bin/sh -c 'echo ok; /bin/busybox | /bin/busybox head -n1' 2>&1) &&
		[ "$(echo "$out" | head -n1)" = ok ] ||
		{ echo "boot: the boot stage's shell does not start in its own tree:" >&2; echo "$out" >&2; exit 1; }
	# and every applet /init calls is in this busybox
	have=$($SUDO chroot "$I" /bin/busybox --list)
	for a in sh mount umount mkdir sed cut awk cat ls head tail grep sleep ifconfig ip udhcpd telnetd \
			setsid findfs killall kill rmdir rm ln cp dmesg switch_root touch tr echo sync reboot; do
		echo "$have" | grep -qx "$a" || { echo "boot: busybox has no $a applet, which /init needs" >&2; exit 1; }
	done
	echo "boot: boot stage checked: $(echo "$out" | sed -n 2p)"
else
	echo "boot: (not checking that the boot stage's shell starts: no root for chroot)"
fi
(cd "$I" && find . | LC_ALL=C sort | cpio --quiet -o -H newc -R 0:0 | gzip -9n) > "$W/initramfs.gz"

# --- will it fit between LK's addresses? -----------------------------------------
# the kernel's own size from its header (image_size, little endian, at byte 16),
# which counts what the file does not (bss)
image_size=$(od -An -t u8 -j 16 -N 8 "$KOUT/arch/arm64/boot/Image" | tr -d ' ')
[ "$image_size" -gt 0 ] || { echo "boot: no image_size in the kernel's header" >&2; exit 1; }
[ $((KERNEL_ADDR + image_size)) -le $((TAGS_ADDR)) ] ||
	{ echo "boot: the kernel ($image_size bytes) runs over LK's device tree address" >&2; exit 1; }
dtb_size=$(stat -c %s "$DTB")
[ $((TAGS_ADDR + dtb_size)) -le $((RAMDISK_ADDR)) ] ||
	{ echo "boot: the device tree ($dtb_size bytes) runs over LK's ramdisk address" >&2; exit 1; }
rd_size=$(stat -c %s "$W/initramfs.gz")
[ $((RAMDISK_ADDR + rd_size)) -le $((RAMDISK_END)) ] ||
	{ echo "boot: the initramfs ($rd_size bytes) runs over cont_splash_mem" >&2; exit 1; }

# --- the Android boot image LK loads ---------------------------------------------
cat "$KOUT/arch/arm64/boot/Image.gz" "$DTB" > "$W/kernel-dtb"
mkbootimg --header_version 0 \
	--kernel "$W/kernel-dtb" --ramdisk "$W/initramfs.gz" \
	--base 0x00000000 --kernel_offset "$KERNEL_ADDR" --ramdisk_offset "$RAMDISK_ADDR" \
	--tags_offset "$TAGS_ADDR" --pagesize 4096 \
	--cmdline "$CMDLINE" -o "$ROOT/out/$NAME.img"

size=$(stat -c %s "$ROOT/out/$NAME.img")
echo "boot: out/$NAME.img ($size bytes; kernel $(cat "$KOUT/kernel.release"), $image_size bytes in memory; initramfs $rd_size bytes)"
