# The Galaxy S9 (Snapdragon: SCV38, SM-G9600; starqltechn) device layer, run
# by the installer inside the build namespace after the GSI part, with $R (the
# root), $DEVSRC (this folder), $DEVROOT (the source tree), $SRC, $P, step and
# ch (see the S9's layer.sh). Everything here is this phone's own: the GSI
# carries none of it.
D=$DEVSRC
KTAG=sdm845-7.1-rc1-r0
KOUT=$DEVROOT/build/linux-$KTAG/out

step "adding the Galaxy S9 (Snapdragon) device layer"
[ -f "$KOUT/kernel.release" ] || {
	echo "no kernel: run devices/samsung-starqltechn/kernel/build-kernel.sh first" >&2
	exit 1
}
KREL=$(cat "$KOUT/kernel.release")

# ztOSIAL: the manifest and this phone's backends
install -d "$R/vendor/ztos"
cp -a "$D/vendor/ztos/." "$R/vendor/ztos/"
chown -R 0:0 "$R/vendor"

cp -a "$D/overlay/." "$R/"                  # firmware, modem, DSP, audio, Bluetooth
chmod 755 "$R"/usr/local/sbin/* 2>/dev/null || true
# The generic Wi-Fi .network would have systemd-networkd take wl* from
# NetworkManager; networkd keeps only the USB link here.
ln -sf /dev/null "$R/etc/systemd/network/20-wlan.network"
ch systemd-sysusers > /dev/null 2>&1 || true

# --- the kernel: ztOS's boot image, so no kernel package ---------------------------
if ch pacman -Qq linux-aarch64 > /dev/null 2>&1; then
	ch pacman --noconfirm -Rdd linux-aarch64 > /dev/null
fi
rm -rf "$R/usr/lib/modules/$KREL"
install -d "$R/usr/lib/modules"
cp -a "$KOUT/modroot/lib/modules/$KREL" "$R/usr/lib/modules/"
chown -R 0:0 "$R/usr/lib/modules/$KREL"
ch depmod -a "$KREL"

# --- the Qualcomm userspace (modem, DSPs, call audio), built here --------------------
step "building the modem and DSP services (qrtr, rmtfs, tqftpserv, hexagonrpcd, q6voiced, 81voltd)"
QS=$DEVROOT/build/starqltechn-userspace
sh "$D/userspace/fetch.sh" "$QS"
rm -rf "$R/usr/src/ztos-qcom"
install -d "$R/usr/src/ztos-qcom"
cp "$QS"/*.tar.gz "$D/userspace/build.sh" "$R/usr/src/ztos-qcom/"
ch sh /usr/src/ztos-qcom/build.sh
rm -rf "$R/usr/src/ztos-qcom"

# --- the boot image, with this root's busybox in its boot stage ----------------------
step "making the boot image (U-Boot, kernel $KREL, boot stage)"
"$D/boot/build-boot.sh" --sysroot "$R" --name ztos-starqltechn-boot
install -d "$STAGEDIR/boot"
cp "$DEVROOT/out/ztos-starqltechn-boot.img" "$STAGEDIR/boot/"

if [ -d "$DEVROOT/build/wallpapers/backgrounds/ztos" ]; then
	install -d "$R/usr/local/share/backgrounds"
	cp -a "$DEVROOT/build/wallpapers/backgrounds/ztos" "$R/usr/local/share/backgrounds/"
fi

# systemd-networkd runs the USB link's DHCP server (10-zboot-usb.network;
# NetworkManager leaves usb0 alone), so the computer gets 172.16.42.2; the
# USB serial port has a login (COM port on Windows, /dev/ttyACM0 on Linux)
DEVICE_UNITS="zboot-usb-gadget zboot-firstboot systemd-networkd serial-getty@ttyGS0
	ztos-starq-firmware rmtfs tqftpserv msm-modem-uim-selection ModemManager ztoscorenetworking 81voltd q6voiced
	hexagonrpcd-sdsp iio-sensor-proxy bluetooth ztos-starq-bluetooth ztos-starq-rtc ztos-starq-rtc-save.timer ztos-starq-charge-led"
