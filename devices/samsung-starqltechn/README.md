# ztOS on the Samsung Galaxy S9, Snapdragon (starqltechn)

The Snapdragon 845 Galaxy S9: **SCV38** (au/KDDI, Japan), **SM-G9600**
(China, Hong Kong, Taiwan) and the other models with an unlockable
bootloader. The US and Canadian Snapdragon S9 (SM-G960U, U1, W) cannot be
unlocked and cannot run this. The Exynos S9 (SM-G960F, N) is `starlte`, the
main ztOS port.

**STATUS_TABLE**

## How it is made

| | |
|---|---|
| Kernel | [sdm845-mainline](https://gitlab.com/sdm845-mainline/linux) 7.1-rc1 (`sdm845-7.1-rc1-r0`, the tree postmarketOS ships for this phone), postmarketOS's config plus [`kernel/ztos.config`](kernel/ztos.config) |
| Kernel patches | brcmfmac for the BCM4361 B2 and the MAX77705 USB-C switch, both from the [Galaxy S9+ mainline port](https://github.com/SheroAbi/galaxy-s9plus-mainline-linux); btbcm's quirk; the S6E3HA8 panel's AOR backlight (Samsung's table, as on the Exynos S9); device tree additions read from the SCV38's own stock tree: [`kernel/patch-dts.py`](kernel/patch-dts.py) |
| Boot | Samsung's bootloader starts U-Boot (2023.01-rc2 with postmarketOS's patches) from BOOT, which starts the kernel, its device tree and ztOS's boot stage from a FIT image: [`boot/build-boot.sh`](boot/build-boot.sh) |
| Boot stage | the S9's zboot ([`initramfs/init`](initramfs/init)): finds the `ZR_ARCH` root in USERDATA; if it cannot, a rescue shell on USB (serial and NCM network, telnet on 172.16.42.1) that saves its log to CACHE |
| Firmware | the phone's own, from its APNHLOS, MODEM, DSP, VENDOR and PERSIST partitions, mounted read-only at every boot ([`ztos-starq-firmware`](overlay/usr/local/sbin/ztos-starq-firmware)); Wi-Fi and Bluetooth addresses from EFS. Nothing is copied into the image and no partition is ever written |
| Modem, DSPs | qrtr, rmtfs (read-only: the modem's EFS copies are never written back), tqftpserv, msm-modem-uim-selection, hexagonrpcd, q6voiced and 81voltd, built from source at Alpine's versions ([`userspace/`](userspace/)); ModemManager |
| ztOSIAL | [`vendor/ztos/manifest.toml`](vendor/ztos/manifest.toml): generic backends, and [`starqltechn.py`](vendor/ztos/ial/starqltechn.py) for the sensors behind iio-sensor-proxy |

## Installing

> **This erases the phone.** Everything in its user data is replaced. Its
> identity (IMEI, modem calibration, Wi-Fi and Bluetooth addresses) and its
> sensor calibration are never written, and are backed up first anyway.
> Only BOOT and USERDATA are written; Android's other partitions stay, as
> ztOS loads the phone's firmware from them.

1. **Unlock the bootloader.** Android: Settings > About phone > Software
   information, tap Build number seven times; Settings > Developer options >
   OEM unlocking. The phone resets itself.
2. **Put TWRP in RECOVERY**: the official
   [TWRP for starqltechn](https://twrp.me/samsung/samsunggalaxys9qcom.html)
   (3.7.0_9-0, `.img.tar`), flashed with Odin in **AP**, *Auto Reboot*
   unticked. Download mode: power off, hold **Volume Down + Bixby** and plug
   the cable in, then **Volume Up**. When Odin says PASS, hold **Volume Down
   + Power** until the screen goes black, then at once **Volume Up + Bixby +
   Power**: TWRP. Do not let Android start, or it puts its own recovery back.
   In TWRP, *Cancel* the password question and *Keep Read Only*.
3. **Build and install.**

On **Linux** (Arch, or anything with the packages of [`docker/Dockerfile`](docker/Dockerfile)):

```sh
devices/samsung-starqltechn/kernel/build-kernel.sh
installer/ztos install --target starqltechn
```

On **Windows** (Docker Desktop, from Git Bash; [Android platform tools](https://developer.android.com/tools/releases/platform-tools) for adb):

```sh
devices/samsung-starqltechn/docker/run.sh devices/samsung-starqltechn/kernel/build-kernel.sh
devices/samsung-starqltechn/docker/run.sh python3 installer/ztos build --target starqltechn --user <you> --password <password>
devices/samsung-starqltechn/docker/run.sh --export build/ztos/starqltechn/root.img build/ztos/starqltechn/stage/boot/ztos-starqltechn-boot.img
devices/samsung-starqltechn/scripts/backup.sh
devices/samsung-starqltechn/scripts/flash-root.sh build/ztos/starqltechn/root.img
devices/samsung-starqltechn/scripts/flash.sh BOOT build/ztos/starqltechn/stage/boot/ztos-starqltechn-boot.img
adb reboot
```

`backup.sh` saves EFS, the modem's partitions, persist, BOOT and the rest to
`stock/starqltechn/` (keep a copy of it). `flash-root.sh` writes USERDATA in
256 MiB pieces, each checked; run it again if the cable comes out and it
carries on. `flash.sh` reads BOOT back after writing it.

The first start takes a minute while the system grows to fill the storage.

## Reaching the phone

- **USB serial:** a login on the phone's USB serial port: a COM port on
  Windows, `/dev/ttyACM0` on Linux (115200 baud).
- **USB network:** `ssh <you>@172.16.42.1` (the computer gets 172.16.42.2).
  Linux and macOS have the NCM driver it needs; Windows 10 does not.
- **TWRP** is always one button combination away: power off (or hold Volume
  Down + Power), then Volume Up + Bixby + Power.

## Going back to Android

From TWRP: `devices/samsung-starqltechn/scripts/flash.sh BOOT stock/starqltechn/boot.img`,
then flash Samsung's firmware for the phone with Odin.
