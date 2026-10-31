#!/bin/bash
# The Galaxy S9 (Snapdragon)'s boot image, for its BOOT partition.
#
#   devices/samsung-starqltechn/boot/build-boot.sh --sysroot <aarch64 root> [--cmdline "..."] [--name N]
#
# The boot stage's busybox is the busybox package's (usr/bin/busybox) from
# the aarch64 root given, the ztOS system being built: on Arch Linux ARM it is
# dynamically linked, so its libraries come from the same root.
# (mkinitcpio-busybox is no use here: it has no mount, switch_root, findfs,
# setsid, telnetd or udhcpd.)
#
# The chain is postmarketOS's for this phone: Samsung's ABL loads BOOT as an
# Android boot image (header v0) whose "kernel" is U-Boot (gzip, with a mock
# device tree after it that ABL fills with the memory map) and whose ramdisk
# is a FIT image; U-Boot runs the FIT's boot script, which boots the FIT's
# kernel, device tree and initramfs (ztOS's boot stage, ../initramfs/init).
#
# Needs: build-kernel.sh run first; aarch64-linux-gnu-gcc (U-Boot), mkimage
# (uboot-tools), mkbootimg (android-tools), dtc, cpio. Out: out/<name>.img.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DEV=$(dirname "$HERE")
ROOT=$(cd "$DEV/../.." && pwd)
KTAG=sdm845-7.1-rc1-r0
KOUT=$ROOT/build/linux-$KTAG/out
UBOOT_VER=2023.01-rc2
# postmarketOS's u-boot-starqltechn 2023.01_rc2 builds from this tarball
UBOOT_SHA512=5e570a0070cd31bb4d9541542532229dbe15e28955428e8a6659de5e4140c89f82d635045d5594e6b9cc6b4bb3037ea4e2c6236433d65a7c814a0ec9c0f32004
UBOOT_URL=https://source.denx.de/u-boot/u-boot/-/archive/v$UBOOT_VER/u-boot-v$UBOOT_VER.tar.gz

NAME=ztos-starqltechn-boot
SYSROOT=
# console=ttyMSM0 first: postmarketOS keeps it to step round a race in the
# display's start (gitlab.freedesktop.org/drm/msm/-/issues/46)
CMDLINE="console=ttyMSM0,115200 console=tty0 loglevel=3 quiet"
while [ $# -gt 0 ]; do
	case $1 in
	--sysroot) SYSROOT=$2; shift ;;
	--cmdline) CMDLINE="$CMDLINE $2"; shift ;;
	--name) NAME=$2; shift ;;
	*) echo "unknown option $1" >&2; exit 2 ;;
	esac
	shift
done
BUSYBOX=$SYSROOT/usr/bin/busybox
[ -n "$SYSROOT" ] && [ -f "$BUSYBOX" ] || { echo "boot: --sysroot <aarch64 root with the busybox package> is needed" >&2; exit 2; }
file -L "$BUSYBOX" | grep -q "ARM aarch64" || { echo "boot: $BUSYBOX is not an aarch64 program" >&2; exit 1; }
for f in "$KOUT/arch/arm64/boot/Image.gz" "$KOUT/arch/arm64/boot/dts/qcom/sdm845-samsung-starqltechn.dtb" \
		"$KOUT/kernel.release"; do
	[ -f "$f" ] || { echo "boot: no $f: run devices/samsung-starqltechn/kernel/build-kernel.sh first" >&2; exit 1; }
done

W=$ROOT/build/starqltechn-boot
mkdir -p "$W" "$ROOT/out"

# --- U-Boot (built once) -------------------------------------------------------
UB=$W/u-boot-v$UBOOT_VER
if [ ! -f "$UB/u-boot.bin" ]; then
	tarball=$ROOT/build/u-boot-v$UBOOT_VER.tar.gz
	if [ ! -f "$tarball" ] || ! echo "$UBOOT_SHA512  $tarball" | sha512sum -c --status; then
		echo "boot: downloading $UBOOT_URL"
		curl -L --fail -o "$tarball.part" "$UBOOT_URL"
		echo "$UBOOT_SHA512  $tarball.part" | sha512sum -c --quiet
		mv "$tarball.part" "$tarball"
	fi
	rm -rf "$UB"
	tar -xzf "$tarball" -C "$W"
	for p in "$HERE"/u-boot/*.patch; do
		patch -d "$UB" -p1 --quiet < "$p"
	done
	echo "boot: building U-Boot $UBOOT_VER for starqltechn"
	# a 2023 tree with today's compilers: their newer warnings are not errors
	U="make -C $UB ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- HOSTCC=gcc KCFLAGS=-Wno-error"
	$U starqltechn_defconfig > /dev/null
	$U -j"$(nproc)" > "$W/u-boot.log" 2>&1 || { tail -30 "$W/u-boot.log" >&2; exit 1; }
fi

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
			setsid findfs killall kill rmdir rm ln cp dmesg switch_root touch tr echo sync; do
		echo "$have" | grep -qx "$a" || { echo "boot: busybox has no $a applet, which /init needs" >&2; exit 1; }
	done
	echo "boot: boot stage checked: $(echo "$out" | sed -n 2p)"
else
	echo "boot: (not checking that the boot stage's shell starts: no root for chroot)"
fi
(cd "$I" && find . | LC_ALL=C sort | cpio --quiet -o -H newc -R 0:0 | gzip -9n) > "$W/initramfs.gz"

# --- FIT: boot script, kernel, device tree, initramfs ---------------------------
cat > "$W/bootscript.sh" <<EOF
setenv bootargs '$CMDLINE'
setenv bootm_size 0x5000000

bootm \$prevbl_initrd_start_addr
EOF
sed -e "s|/incbin/(\"bootscript.sh\")|/incbin/(\"$W/bootscript.sh\")|g" \
	-e "s|/incbin/(\"vmlinuz\")|/incbin/(\"$KOUT/arch/arm64/boot/Image.gz\")|" \
	-e "s|/incbin/(\"/boot/dtbs/qcom/sdm845-samsung-starqltechn.dtb\")|/incbin/(\"$KOUT/arch/arm64/boot/dts/qcom/sdm845-samsung-starqltechn.dtb\")|" \
	-e "s|/incbin/(\"initramfs\")|/incbin/(\"$W/initramfs.gz\")|" \
	"$HERE/boot_image.its" > "$W/boot_image.its"
grep -q "$W/initramfs.gz" "$W/boot_image.its" && grep -q "Image.gz" "$W/boot_image.its" ||
	{ echo "boot: boot_image.its did not take the paths" >&2; exit 1; }
mkimage -q -f "$W/boot_image.its" "$W/boot_image.itb"

# --- the Android boot image ABL loads ------------------------------------------
dtc -q -I dts -O dtb -o "$W/payload_mock.dtb" "$HERE/payload_mock.dts"
gzip -9nc "$UB/u-boot.bin" > "$W/u-boot.bin.gz"
cat "$W/u-boot.bin.gz" "$W/payload_mock.dtb" > "$W/kernel-payload"
# offsets: postmarketOS's deviceinfo for this phone, which are also the stock
# BOOT's; board, OS version and patch level copied from the SCV38's stock BOOT
mkbootimg --header_version 0 \
	--kernel "$W/kernel-payload" --ramdisk "$W/boot_image.itb" \
	--base 0x00000000 --kernel_offset 0x00008000 --ramdisk_offset 0x02000000 \
	--second_offset 0x00f00000 --tags_offset 0x01e00000 --pagesize 4096 \
	--board SRPQJ19B001 --os_version 10.0.0 --os_patch_level 2021-06 \
	--cmdline "" -o "$ROOT/out/$NAME.img"

size=$(stat -c %s "$ROOT/out/$NAME.img")
# BOOT is 64 MiB on this phone
[ "$size" -le $((64 * 1024 * 1024)) ] || { echo "boot: $NAME.img is $size bytes, BOOT holds 64 MiB" >&2; exit 1; }
echo "boot: out/$NAME.img ($size bytes, kernel $(cat "$KOUT/kernel.release"))"
