## Installing ztOS on the Microsoft Lumia 950 (talkman)

> **This erases the phone.** Windows' system and data partitions (MainOS and Data) are
> replaced. The phone's identity (IMEI, modem calibration, Wi-Fi and Bluetooth addresses)
> and everything else up to and including EFIESP stay where they are. Only EFIESP gets new
> files, and it is backed up first with the rest of the phone. Never write the DPP
> partition: it holds calibration that cannot be had back.

Tried on one phone, whose USB reports **RM-1105**. Other Lumia 950 models (RM-1104, RM-1106,
RM-1116, RM-1118) use the same board and may work, but none has been tried. The 950 XL
(cityman) is a different phone and this does not support it.

Read the status table in the [README](README.md) first: this port has no microphone or modem yet.

### What you need

- A computer with Windows 10 or 11, 60 GB free for the build and 35 GB more for the backup
- A USB-C data cable (some only charge)
- The phone charged above 50 %, with an unlocked bootloader (step 3)
- About 3 hours the first time, mostly waiting for the build

The backup and partition steps use PowerShell as administrator, so this guide is for
Windows. The build itself runs in Docker.

### 1. Install the tools on your computer

1. [Git for Windows](https://git-scm.com/download/win): its Git Bash runs every `sh` command below.
2. [Docker Desktop](https://www.docker.com/products/docker-desktop/), started once and left running.
3. Google's [Android platform tools](https://developer.android.com/tools/releases/platform-tools), with the folder holding `fastboot` in your PATH.
4. [Python 3](https://www.python.org/downloads/windows/), ticking "Add to PATH".
5. [WPInternals](https://github.com/ReneLergner/WPinternals), to unlock the phone and put it in mass storage mode.

Open **Git Bash** and check:

```sh
docker info --format '{{.ServerVersion}}'
fastboot --version
python --version
```

### 2. Get the port

```sh
git clone -c core.autocrlf=false --branch talkman-port https://github.com/Davitekk/ztOS.git
cd ztOS
git clone https://github.com/Android4Lumia950/installer ../a4l-installer
git -C ../a4l-installer checkout be3ed23
```

The second repository holds the bootloader files this port uses (BootShim, LK with fastboot,
the developer menu). `install-lk.ps1` checks each file's checksum before using it.

(`core.autocrlf=false` keeps the scripts' Unix line endings on Windows: the build runs them in
Linux.)

### 3. Unlock the bootloader

Use WPInternals' own guide. The phone this was tried on was already unlocked, so this step is
the one part of the guide that was not run for this port.

### 4. Put the phone in mass storage mode

In WPInternals, switch the phone to **Mass Storage Mode**. Windows then sees the phone's
storage as a disk and may show extra drive letters. **If Windows offers to format anything,
click Cancel.**

### 5. Back up the whole phone

In **PowerShell as administrator**, from the `ztOS` folder, with a folder on a drive with 35 GB free:

```sh
powershell -ExecutionPolicy Bypass -File devices\microsoft-talkman\tools\backup-emmc.ps1 -Out D:\ztos-talkman-backup
```

This reads the entire storage (about 30 minutes) and opens the disk read-only. The copy
holds the phone's identity, so keep it private. It is your way back to Windows.

### 6. Put the bootloader on the phone

Still in mass storage mode, and still in PowerShell as administrator:

```sh
powershell -ExecutionPolicy Bypass -File devices\microsoft-talkman\tools\install-lk.ps1 -Data ..\a4l-installer\DATA -Ui ..\a4l-installer\ui -Backup D:\ztos-talkman-backup
```

This changes only EFIESP. It keeps WPInternals' route back to flash mode working.

### 7. Build ztOS

In **Git Bash**. Choose the user name and password you will log in with (the password is also
for `sudo`), and put them in the second command:

```sh
devices/microsoft-talkman/docker/run.sh devices/microsoft-talkman/kernel/build-kernel.sh
devices/microsoft-talkman/docker/run.sh python3 installer/ztos build --target talkman --user YOURNAME --password YOURPASSWORD
devices/microsoft-talkman/docker/run.sh devices/microsoft-talkman/boot/build-boot.sh --sysroot build/ztos/talkman/root --firmware build/talkman-boot/firmware --name ztos-talkman-rescue --cmdline "zboot.rescue=1 zboot.noretry=1 loglevel=7"
devices/microsoft-talkman/docker/run.sh --export out/ztos-talkman-boot.img out/ztos-talkman-rescue.img build/ztos/talkman/root.img
```

| Step | Time the first time, on 12 threads |
|---|---|
| The kernel | 5 to 10 minutes |
| The system | about 15 minutes |
| The rescue image and the export | a few minutes |

By default the build uses 6 CPUs and 6 GB of memory, so the computer stays usable; with more
to spare, set `ZTOS_BUILD_CPUS=12 ZTOS_BUILD_MEM=14g` first and it goes much faster.
Everything builds in a Docker volume (`ztos-talkman-build`) that is kept between runs. The
exported files land in `out/` and `build/ztos/talkman/`.

**Building again after changing something:** add `--fresh` to the `installer/ztos build` command.
Without it the build reuses the system image it already has, finishes in a minute, and your
changes outside the kernel are not in it.

### 8. Install it

Restart the phone: in WPInternals leave mass storage mode, or hold **Power** for about 15
seconds until it vibrates. With no `boot` partition to start from, LK stays in fastboot, with
the screen dark or showing little. Then:

```sh
fastboot devices
fastboot boot out/ztos-talkman-rescue.img
```

`fastboot devices` should list one device. After about 30 seconds the phone is a network
device, 172.16.42.1 (the computer gets 172.16.42.2). Then:

```sh
python devices/microsoft-talkman/tools/install-talkman.py --root build/ztos/talkman/root.img --boot out/ztos-talkman-boot.img --backup D:/ztos-talkman-backup
```

It writes the new partition table (keeping the old one in the backup folder), writes the system
over USB and reads it back (about 15 minutes), then flashes the boot image and restarts. It
stops at the first thing that does not match. If the cable comes out, start again from
`fastboot boot`. Your computer's copy of `root.img` is 10 GB.

If the script reports that the phone does not respond, the power controller may not have answered
on that start (see step 9). Send `reboot -f` over the phone's shell, or hold Power for 15 seconds,
then repeat `fastboot boot`.

### 9. Start ztOS

The first start usually reaches the shell in about a minute, but the screen may stay black for
up to 2 minutes:

- On some starts the phone's power controller does not answer. The boot stage notices and
  restarts by itself, sometimes more than once. Each try vibrates.
- Every start has a 20 second wait for the battery gauge.

Then the shell appears. Over the USB cable you can also log in: `ssh YOURNAME@172.16.42.1`,
and a serial console appears as a COM port.

An earlier build was rebuilt from scratch and installed on the test phone with these steps on
2026-11-04: it reached the shell, and scrolling Start measured 59.8 fps. Wi-Fi, vibration, the
motion sensors and sound came after that, and were put on that same installation by hand, so this
guide has not yet been run from the start with them.

Connect to Wi-Fi from Settings. On the command line, a password with a `!` in it needs single
quotes: bash treats `!` in double quotes as a history command.

### If something goes wrong

| What you see | What to do |
|---|---|
| `fastboot devices` lists nothing | Windows may need a driver for the Android bootloader interface; try another cable or port. Hold Power for 15 seconds to restart |
| The phone stays black and off USB, after a test kernel or a bad flash | Hold Power for 15 seconds. If it still does not come up, go to mass storage mode with WPInternals and write a known good boot image to the partition named `boot` |
| `the disk is not this phone's` | The script only writes to a disk of this phone's exact size. Stop and check which device is connected |
| `$'\r': command not found` | The clone has Windows line endings: clone again with `-c core.autocrlf=false` |
| The build fails at its start | Docker Desktop must be running; check with `docker info` |
| No `ssh` over USB | Set that USB network adapter to automatic (DHCP): the phone gives it 172.16.42.2 |
| Pressing both volume keys in LK | Avoid it: that enters emergency download mode |

### Testing your own kernel safely

Erase the boot partition, so a kernel that hangs falls back to fastboot rather than leaving the
phone stuck: `blkdiscard -z /dev/disk/by-partlabel/boot`, restart, then `fastboot boot` your image
with `oops=panic` on its command line. Flash it only once it runs.

### Back to Windows

The full backup from step 5 is an image of the whole storage. With the phone in mass storage mode,
write `gpt-before-ztos-primary.bin` and `gpt-before-ztos-backup.bin` back to restore the partition
table, then flash a Windows FFU with WPInternals. This route has not been tried on this phone.
