# The Lumia 950 (talkman) device layer, run by the installer inside the build
# namespace after the GSI part, with $R (the root), $DEVSRC (this folder),
# $DEVROOT (the source tree), $SRC, $P, step and ch (see the S9's layer.sh).
# Everything here is this phone's own: the GSI carries none of it.
D=$DEVSRC
KOUT=$DEVROOT/build/linux-talkman/out

step "adding the Lumia 950 device layer"
[ -f "$KOUT/kernel.release" ] || {
	echo "no kernel: run devices/microsoft-talkman/kernel/build-kernel.sh first" >&2
	exit 1
}
KREL=$(cat "$KOUT/kernel.release")

# ztOSIAL: the manifest
install -d "$R/vendor/ztos"
cp -a "$D/vendor/ztos/." "$R/vendor/ztos/"
chown -R 0:0 "$R/vendor"

cp -a "$D/overlay/." "$R/"
chmod 755 "$R"/usr/local/sbin/* 2>/dev/null || true
chmod 755 "$R"/usr/local/bin/ztcamera-route

# --- Wi-Fi: this phone's own RF calibration, as ath10k's board file ----------------
# With the generic board.bin the chip works, but it finds no 5 GHz network. The file is the
# phone maker's: fetched here, not kept in this repository. It also sets the MAC address, the same
# on every phone, so NetworkManager gives each phone its own (the overlay's ztos-talkman-mac.conf).
BDWLAN=$DEVROOT/build/talkman-boot/bdwlan30.bin
install -d "$(dirname "$BDWLAN")"
curl -sSL --fail --retry 3 -o "$BDWLAN" \
	https://raw.githubusercontent.com/Android4Lumia950/firmware-microsoft-talkman/e9e9fac86db9dfd0a1992062987cfcbfd92403c7/bdwlan30.bin
echo "53016024e0311024fa661cf10c607370e2ce296f350d487429dc402562f7b395  $BDWLAN" | sha256sum -c - > /dev/null
install -m644 "$BDWLAN" "$R/usr/lib/firmware/ath10k/QCA6174/hw3.0/board.bin"

# --- Sound: the audio DSP's firmware, under the name the kernel's device tree asks for ------
ADSP=$DEVROOT/build/talkman-boot/qcadsp8992.mbn
curl -sSL --fail --retry 3 -o "$ADSP" \
	https://raw.githubusercontent.com/Android4Lumia950/firmware-microsoft-talkman/e9e9fac86db9dfd0a1992062987cfcbfd92403c7/qcadsp8992.mbn
echo "1266429dd8a9d746ceff2d712bde7edc580c25fc85f3f0f4515f4b867a18e12f  $ADSP" | sha256sum -c - > /dev/null
install -m644 "$ADSP" "$R/usr/lib/firmware/qcadsp8994.mbn"
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

# --- the boot image, with this root's busybox in its boot stage ----------------------
# The GPU's driver is built in and opens its microcode as the console starts,
# before the root is mounted: the boot stage carries it.
step "making the boot image (kernel $KREL, boot stage)"
FW=$DEVROOT/build/talkman-boot/firmware
rm -rf "$FW"
install -d "$FW/qcom"
cp -L "$R"/usr/lib/firmware/qcom/a420_p* "$FW/qcom/"
"$D/boot/build-boot.sh" --sysroot "$R" --firmware "$FW" --name ztos-talkman-boot
install -d "$STAGEDIR/boot"
cp "$DEVROOT/out/ztos-talkman-boot.img" "$STAGEDIR/boot/"

if [ -d "$DEVROOT/build/wallpapers/backgrounds/ztos" ]; then
	install -d "$R/usr/local/share/backgrounds"
	cp -a "$DEVROOT/build/wallpapers/backgrounds/ztos" "$R/usr/local/share/backgrounds/"
fi

# systemd-networkd runs the USB link's DHCP server (10-zboot-usb.network;
# NetworkManager leaves usb0 alone), so the computer gets 172.16.42.2; the
# USB serial port has a login (COM port on Windows, /dev/ttyACM0 on Linux)
DEVICE_UNITS="zboot-usb-gadget zboot-firstboot systemd-networkd serial-getty@ttyGS0 bluetooth ztos-talkman-wifi ztos-talkman-audio"
