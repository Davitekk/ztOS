# ztOS on the Microsoft Lumia 950 (talkman)

The Snapdragon 808 Lumia 950, booted through BootShim and LK on the phone's own UEFI, running
ztOS on the Android4Lumia950 mainline kernel (Linux 7.3-rc2). See [INSTALL.md](INSTALL.md).

This is an early port. The display, touch, charging, USB and vibration work well, both cameras give
pictures, Wi-Fi works and the speaker plays, but **there is no microphone or modem yet**, so it is
not usable as a phone.

## Status

Tried on one phone, whose USB reports RM-1105. **Works**: tried, and does what it should.
**Partial**: some of it works; the notes say what. **Untested**: written or detected, not tried
with real use. **Not working**: tried and failing, or not started; the notes say which.

### Hardware

| Category | Feature | Status | Notes |
|---|---|---|---|
| Boot | Booting from internal storage | Partial | Works, but the power controller (RPM) does not answer on some starts, 3 of the last 10 here; the boot stage restarts by itself, so a start takes 80 s and sometimes 3 minutes or more. Cause unknown |
| Display | Panel, 1440x2560 | Works | Dual-DSI command-mode AMOLED at 60 Hz, clean picture |
| Display | Brightness | Works | |
| Display | GPU | Works | Adreno 418 run as A430 (freedreno, GLES 3.0). Scrolling Start measured at about 60 fps |
| Input | Touchscreen | Works | Synaptics S3708 |
| Input | Power and volume keys | Works | |
| Input | Camera button | Untested | No longer restarts the phone; not mapped to anything |
| Input | Vibration | Works | PMI8994 haptics, a small driver here. Each start is a 40 ms kick at 3.6 V, as the motor takes 60 ms to spin up and the system's taps last 12 ms; it then runs at up to 2.9 V. Measured with the motion chip, a tap moved 0.2 m/s2 before this and moves 8.8 now. Stops by itself after 15 s at most |
| Power | CPU, frequency scaling | Not working | No driver. The cores stay at the bootloader's clocks, measured at about 785 MHz (little) and 191 MHz (big), so programs are kept on the little cores |
| Power | Battery and charging | Works | PMI8994 gauge and charger: USB charging tried, limits set to 4.35 V, 1.5 A. The gauge adds 20 s to every start |
| Power | Hardware watchdog | Works | ztOS already asks systemd to keep it fed, so a hard hang restarts the phone within about 30 s. One accidental crash during this work came back by itself in under a minute. Not hung on purpose |
| Power | Power off | Untested | The kernel now tells the power chip to shut down instead of resetting, which is why power off used to restart the phone. Rebooting is tried and still works. Power off itself is not tried yet |
| Power | Sleep (suspend) | Not working | Tried with a timed `s2idle`: with USB and PCIe kept up, the phone goes to sleep and the RTC wakes it, then it restarts while resuming, with no crash record. This kernel also has no CPU idle states, so sleep would save little yet |
| Network | USB networking | Works | RNDIS: 172.16.42.1 (the computer gets 172.16.42.2), plus a serial console |
| Network | Wi-Fi | Works | QCA6174 on PCIe with ath10k, started after boot. Joins a network from Settings and reaches the internet: `ping google.com` 9 of 9, about 10 ms. Finds 2.4 and 5 GHz networks. PCIe link at Gen 1 |
| Network | Bluetooth | Works | QCA6174 on `blsp2_uart2`. Pairing and audio tried. Its address is made from the installation's machine id, not the phone's own |
| Modem | SIM, mobile data, SMS, calls | Not working | The modem boots by hand, with its firmware and `rmtfs` on copies of its file systems, and answers AT commands on the `DATA1` to `DATA4` channels. The SIM card itself works: it answers raw commands sent through the modem (`AT+CSIM`), so the slot and its power are fine. But the modem's own SIM manager stays at `SIM busy`, so there is no signal, and its usual control services (DMS, NAS, WDS, UIM) never appear. Not started in a normal boot. `tools/modem-start.sh` starts it by hand and says what was tried. |
| Audio | Speaker | Works | TAS2553 amp behind the audio DSP, through PipeWire and its volume. Checked by recording it with a microphone beside the phone: tones at 440, 1500 and 3000 Hz, clean and loud |
| Audio | Earpiece, microphones, headphones | Not working | On the WCD9330 codec. Its bus comes up by hand and the codec answers, and capture runs, but every sample is 0. Off in a normal boot: `kernel/wip-codec-card.dtsi` has how to try it and what was measured |
| Camera | Rear, 21 MP | Works | The preview does not look good. Real pictures; preview about 6 fps and soft. Focus is fixed (no lens driver), and photos are about 5 MP as the sensor's cells are not demosaiced. First pictures looked sharp at table distance |
| Camera | Front, 5 MP | Works | The preview does not look good. Real pictures, in a dim room too; preview about 8 fps. Photos about 1.3 MP |
| Camera | Iris camera | Not working | Found, no picture yet. I2C 0x36 on CCI0, ID 0x0861, set up for 1928x1088 RAW10, with SMIA's settings registers but none of its capability tables, so the `ccs` driver cannot run it. It shares CSI2 with the front camera in combo mode (clock on PHY lane 3, data on lane 4), which camss does not do: tried by hand, the lane shows activity, and no frame arrived |
| Camera | Flash | Not working | The driver chip answers at 0x30 on the first camera bus, with ID 0x16. It matches neither of the two close candidates checked, AS3643 and AS3649, so nothing was written to it: a wrong current setting could burn the LEDs. Its torch input alone gives no light. It needs the chip identified |
| Sensors | Magnetometer | Partial | AK8975: reads through ztOSIAL; no calibration or mounting matrix |
| Sensors | Pressure | Untested | ZPA2326: reads a value |
| Sensors | Ambient light, auto brightness | Works | APDS-9930. Auto brightness follows the room, with its switch in Settings. Tried in a daylit room: the screen goes to its level by itself, and readings do not rise with the screen. A dark room and sunlight were only tried with simulated readings. The lux scale is an estimate (`LUX_PER_COUNT` in `ztos-talkman-light`), not measured. The sensor's first probe sometimes times out at boot, so the daemon tries it again |
| Sensors | Proximity | Untested | APDS-9930: reads about 45, not tried with anything near it. Its infrared LED pulses only while proximity is being read |
| Sensors | Accelerometer, gyroscope | Partial | Not the MPU-6500 the device tree names but an ICM-20x48 family chip, with a small driver here. Lying still it reads 9.6 m/s2 down its Z axis, and the gyroscope and temperature are sensible. No mounting matrix yet: only Z has been checked, with the phone flat, so X and Y may be swapped or reversed |
| Other | NFC | Partial | The chip turns on and polls, on the kernel's NXP NCI driver. Reading a tag: not tried yet. `tools/nfc-poll.py` tests it. There is no NFC app |
| Other | FM radio | Untested | The device appears |
| Location | GPS | Not working | Depends on the modem |
| Storage | Internal, 32 GB | Works | ztOS takes MainOS and Data; the system fills it on first start |
| Storage | microSD | Works | Tried with an 8 GB FAT32 card: a 64 MB file read back the same, reading at 22 MB/s and writing at 5 MB/s. It appears as `SD card` in the home folder, so in the Files app. Taking a card out while running is not tried |

### Software

| Feature | Status | Notes |
|---|---|---|
| ztMETRO, the shell | Works | 59.8 fps while scrolling Start, measured on a fresh install; 2 late frames in 30 s |
| ztCamera | Works | The preview does not look good. Live viewfinder, front and rear switch, photos |
| Sound in ztMETRO | Works | Through PipeWire and WirePlumber |
| Android apps (Waydroid) | Untested | Its first-start download needs Wi-Fi, which now works; not tried yet |
| ztOSIAL (`ztos-ial test`) | Partial | All but one check passed on a fresh install; the one that fails looks for cpufreq clusters |

## How it is made

| | |
|---|---|
| Boot chain | UEFI, Windows Boot Manager, [BootShim, LK with fastboot](https://github.com/Android4Lumia950/installer) |
| Kernel | [Android4Lumia950/linux](https://github.com/Android4Lumia950/linux), a pinned commit, plus the patches in [`kernel/`](kernel) |
| Build | [`kernel/build-kernel.sh`](kernel/build-kernel.sh), [`docker/`](docker); all drivers built in |
| Device layer | [`layer.sh`](layer.sh), [`overlay/`](overlay), [`vendor/ztos/manifest.toml`](vendor/ztos/manifest.toml) |
| Install | [`tools/`](tools) |

### The patches, and what each was for

| Patch | Why |
|---|---|
| `patch-dts.py` | This phone's IDs for LK, battery limits |
| `patch-dsi-cfg.py`, `patch-mdp5-cfg.py` | The panel: the right DSI settings for this chip; no destination split, which shifted the picture |
| `patch-msm-hw-done.py`, `patch-panel-clock.py` | 60 fps: frames were rejected, and the link had too little time between transfers |
| `patch-mmcc-gpu.py`, `patch-gpu-a418.py` | The GPU on MSM8992 |
| `patch-dwc3-usb-sel.py` | USB on a direct boot: registers only LK's fastboot mode set |
| `patch-pon-reset.py` | A hard reset on restart |
| `patch-camera-key.py` | Removes the tree's debugging aid that restarted on the camera button |
| `patch-camera.py`, `camss-msm8994.patch`, `camera-talkman.dtsi` | The cameras: see the comments in `patch-camera.py` |
| `patch-hw.py`, `hw-talkman.dtsi`, `drivers/` | The motion chip, the motor, PCIe and Wi-Fi's power: see the comments in each |

### Good to know when working on it

- The cameras write to physical memory with no IOMMU, as this phone's secure firmware refuses to
  set the camera's IOMMU up, and 256 MB of memory is reserved for them (`cma=256M`).
- `/dev/mem` reads of a camera block whose clocks are off panic the kernel. Only read them while
  a stream is running.
- The full-size sensor readout is more than the camera block's bus takes, so previews are scaled
  on the sensor. `ztcamera-route` holds all of this.
- `/sys/fs/pstore` keeps the kernel log of the last start, so a restart can be read afterwards (a
  power controller retry overwrites it).
- Kernels hang: test them from RAM with the boot partition empty (see [INSTALL.md](INSTALL.md)).
- The audio DSP starts after boot, from `ztos-talkman-audio.service`. Its memory must be at
  0x0ce00000: at the kernel tree's address the phone restarts with no record. PipeWire must send it
  16 bits (`51-ztos-talkman.conf`): offered 24, it plays 48 dB too quiet.
- The secure firmware refuses the DSP unless the crypto engine's clock is on. That clock must not
  be under `clocks` in the device tree: the changed driver order makes the power controller stop
  answering on most boots. It is taken when the DSP starts (`ztos,crypto-clock`, `patch-hw.py`).
- The modem's boot image goes in ordinary memory: the kernel tree's place for it is in the phone's
  own "removed" range, 0x5000000 to 0x7200000, and writing there restarts the phone. Its firmware
  is `qcdsp1v28992.mbn` and `qcdsp28992.mbn` from Android4Lumia950/firmware-microsoft-talkman.
- **Never let `rmtfs` near the partitions `MODEM_FS1`, `MODEM_FS2`, `MODEM_FSC` or `MODEM_FSG`** (its
  `-P`): they hold the phone's identity. Copy them to files, read-only, and run `rmtfs -o` on those.
- PCIe starts after boot, from `ztos-talkman-wifi.service`, not while the kernel starts: Wi-Fi's
  firmware is on the root, and a fault then comes with SSH up. `lspci` should list the QCA6174.
- The controller needs its core reset (`PCIE_0_CORE_RESET`, which the kernel's table left out).
  Without it the link reaches L0, yet every read of the card returns all ones and no error.
- Bluetooth's UART must not use DMA, or the chip never answers. `ztos-talkman-bluetooth` starts the
  chip again after Wi-Fi has its 3.3 V on, and gives it its address.
- `/dev/input/event0` is now the motor: the power key moved to `event1`.
- Wi-Fi's MAC address comes from the board file, so it would be the same on every phone.
  NetworkManager is set to give each phone a stable one of its own.
