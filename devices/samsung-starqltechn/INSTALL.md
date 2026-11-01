## Installing ztOS on the Galaxy S9, Snapdragon (starqltechn)

> **This erases the phone.** Android's data and everything in the phone's
> storage are replaced. The phone's identity (IMEI, modem calibration, Wi-Fi
> and Bluetooth addresses) and its sensor calibration are never written, and
> are backed up to your computer first anyway. Only BOOT and USERDATA are
> written: Android's other partitions stay, because ztOS loads the phone's own
> firmware from them.

Only the Snapdragon Galaxy S9 with an unlockable bootloader works: **SCV38**
(au, Japan) and **SM-G9600** (China, Hong Kong, Taiwan). The US and Canadian
SM-G960U, U1 and W cannot be unlocked. The Exynos S9 (SM-G960F, N) is
`starlte`, the main ztOS port, with its own guide.

### What you need

- A computer with Windows 10 or 11 (tested), or Linux, with 60 GB free and an internet connection
- A USB-C data cable (some only charge)
- The phone charged above 50 %
- About 3 hours the first time, mostly waiting for the build

### 1. Install the tools on your computer

On **Windows**:

1. [Git for Windows](https://git-scm.com/download/win): its Git Bash runs every command below.
2. [Docker Desktop](https://www.docker.com/products/docker-desktop/), started once and left running.
3. Google's [Android platform tools](https://developer.android.com/tools/releases/platform-tools), with the folder holding `adb.exe` added to your `PATH`.
4. Samsung's [USB driver for Windows](https://developer.samsung.com/android-usb-driver) and Odin, Samsung's flashing tool (3.14 or later; Samsung has no official download page, so take it from a well-known source).

Open **Git Bash** and check:

```sh
docker info --format '{{.ServerVersion}}'
adb version
```

On **Linux**, install Docker and `adb` (Arch: `sudo pacman -S docker android-tools`; Debian and Ubuntu: `sudo apt install docker.io adb`), and Heimdall instead of Odin (`heimdall`, `heimdall-flash`).

### 2. Get the port

```sh
git clone -c core.autocrlf=false --branch starqltechn-port https://github.com/Davitekk/ztOS.git
cd ztOS
```

(`core.autocrlf=false` keeps the scripts' Unix line endings on Windows: the
build runs them in Linux.)

### 3. Unlock the bootloader

1. Back up the phone. Unlocking erases it.
2. In Android: Settings > About phone > Software information, tap **Build number** seven times.
3. Settings > Developer options > **OEM unlocking**: on. No such switch? Connect to Wi-Fi and wait: Samsung can take up to 7 days after setup to show it.
4. Turn the phone off. Hold **Volume Down + Bixby** and plug in the USB cable.
5. On the warning screen, long-press **Volume Up** to unlock. The phone erases itself and restarts.
6. Go through Android's setup quickly, and check that OEM unlocking is still on.

### 4. Put TWRP in RECOVERY

1. Download the official TWRP for the Galaxy S9 (Qualcomm), [twrp.me/samsung/samsunggalaxys9qcom.html](https://twrp.me/samsung/samsunggalaxys9qcom.html): the latest `.img.tar` (3.7.0_9-0 is the one tested).
2. Turn the phone off. Hold **Volume Down + Bixby** and plug in the cable, then press **Volume Up**: download mode.
3. In Odin, put the TWRP `.img.tar` in **AP**, untick **Auto Reboot** in Options, and press Start. (Linux: `heimdall flash --RECOVERY recovery.img --no-reboot`, with `recovery.img` taken out of the `.tar`.)
4. When Odin says PASS, hold **Volume Down + Power** until the screen goes black, then at once **Volume Up + Bixby + Power** until TWRP appears. If Android starts instead, it puts its own recovery back: repeat this step.
5. In TWRP, *Cancel* the password question and choose *Keep Read Only*.

From now on, TWRP is always one button combination away: power off, then hold **Volume Up + Bixby + Power**.

### 5. Back up the phone's identity

With the phone in TWRP and plugged in:

```sh
adb devices
devices/samsung-starqltechn/scripts/backup.sh
```

`adb devices` should list one device, as `recovery`. The backup saves EFS
(IMEI, Wi-Fi and Bluetooth addresses), the modem's partitions, persist, BOOT
and the rest that cannot be had back to `stock/starqltechn/`, each read twice
and checked. Keep a copy of that folder somewhere safe. It stays out of git.

### 6. Build ztOS

Choose the user name and password you will log in with (the password is also
for `sudo`), and put them in the second command:

```sh
devices/samsung-starqltechn/docker/run.sh devices/samsung-starqltechn/kernel/build-kernel.sh
devices/samsung-starqltechn/docker/run.sh python3 installer/ztos build --target starqltechn --user YOURNAME --password YOURPASSWORD
devices/samsung-starqltechn/docker/run.sh sh devices/samsung-starqltechn/scripts/root-chunks.sh build/ztos/starqltechn/root.img build/ztos/starqltechn/root-chunks
devices/samsung-starqltechn/docker/run.sh --export build/ztos/starqltechn/root-chunks build/ztos/starqltechn/stage/boot/ztos-starqltechn-boot.img
```

| Step | Time the first time |
|---|---|
| The kernel | 30 to 60 minutes |
| The system | 30 to 60 minutes |
| The pieces and the export | about 10 minutes |

Everything builds in a Docker volume (`ztos-starqltechn-build`) that is kept
between runs, so later builds are much quicker. The system image is 10 GB,
mostly empty; it comes out as about 2.5 GB of checked pieces in
`build/ztos/starqltechn/root-chunks`.

### 7. Install it

With the phone in TWRP and plugged in:

```sh
devices/samsung-starqltechn/scripts/flash-root.sh build/ztos/starqltechn/root-chunks
devices/samsung-starqltechn/scripts/flash.sh BOOT build/ztos/starqltechn/stage/boot/ztos-starqltechn-boot.img
adb reboot
```

`flash-root.sh` writes the system to USERDATA in 256 MiB pieces, each read
back and checked: 10 to 20 minutes. If the cable comes out, run it again and
it carries on. `flash.sh` writes ztOS's boot image to BOOT and reads it back.

### 8. Start ztOS

The first start takes about a minute while the system grows to fill the
storage. Then log in with your user and password, and the Welcome app shows
how ztOS works. With internet, Android apps set themselves up in the
background on the first start (Waydroid downloads about 1 GB once).

Over the USB cable the phone is also a network: `ssh YOURNAME@172.16.42.1`
(the computer gets 172.16.42.2), and a serial console (a COM port on
Windows, `/dev/ttyACM0` on Linux).

### Upgrading to a new version, keeping your data

A new ztOS version is a new system image, and writing it replaces USERDATA.
`upgrade.sh` keeps your data across it: your home (settings, files, Android's
apps), Wi-Fi networks, Bluetooth pairings, calls and messages, the access
point and your password. Build the new version as in step 6, with the same
user name, then:

1. With the old ztOS running and the cable in:

   ```sh
   devices/samsung-starqltechn/scripts/upgrade.sh save
   ```

2. In TWRP, step 7.
3. When the new ztOS shows its lock screen:

   ```sh
   devices/samsung-starqltechn/scripts/upgrade.sh restore backups/starqltechn/ztos-data-DATE.tar.gz
   ```

   The phone restarts with your data. The saved file holds Wi-Fi passwords and
   messages: it stays in `backups/`, out of git.

### If something goes wrong

| What you see | What to do |
|---|---|
| `the phone is not in TWRP` | Start TWRP (Volume Up + Bixby + Power), try another cable or USB port, then `adb devices` |
| `stock/starqltechn/... missing: run backup.sh first` | Step 5: `flash.sh` will not write BOOT without the backup |
| `USERDATA is still mounted in TWRP` | In TWRP, Mount, untick Data, then run `flash-root.sh` again |
| The build fails at its start on Windows | Docker Desktop must be running; check with `docker info` |
| `$'\r': command not found` | The clone has Windows line endings: clone again with `-c core.autocrlf=false` (step 2) |
| The phone shows ztOS's rescue screen | The system was not found: run step 7 again from TWRP |
| No `ssh` over USB | The phone gives the computer 172.16.42.2: set that USB network adapter to automatic (DHCP) |

### Back to Android

From TWRP, put Samsung's kernel back, then flash Samsung's firmware for your
model with Odin from download mode:

```sh
devices/samsung-starqltechn/scripts/flash.sh BOOT stock/starqltechn/boot.img
```
