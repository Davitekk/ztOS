# ztOS on the Microsoft Lumia 950 (talkman)

The Snapdragon 808 Lumia 950, booted through BootShim and LK on the phone's own UEFI, running
ztOS on the Android4Lumia950 mainline kernel (Linux 7.3-rc2). See [INSTALL.md](INSTALL.md).

This is an early port. The display, touch, charging and USB work well, and both cameras give
pictures, but **there is no Wi-Fi, sound or modem yet**, so it is not usable as a phone.

## Status

Tried on one phone, whose USB reports RM-1105, on a fresh install of this branch. **Works**: tried, and does what it should.
**Partial**: some of it works; the notes say what. **Untested**: written or detected, not tried
with real use. **Not working**: tried and failing, or not started; the notes say which.

### Hardware

| Category | Feature | Status | Notes |
|---|---|---|---|
| Boot | Booting from internal storage | Partial | Works, but the power controller (RPM) does not answer on about half of all starts; the boot stage restarts by itself, so a start can take 2 minutes. Cause unknown |
| Display | Panel, 1440x2560 | Works | Dual-DSI command-mode AMOLED at 60 Hz, clean picture |
| Display | Brightness | Works | |
| Display | GPU | Works | Adreno 418 run as A430 (freedreno, GLES 3.0). Scrolling Start measured at about 60 fps |
| Input | Touchscreen | Works | Synaptics S3708 |
| Input | Power and volume keys | Works | |
| Input | Camera button | Untested | No longer restarts the phone; not mapped to anything |
| Input | Vibration | Not working | Not started: no device shows up |
| Power | CPU, frequency scaling | Not working | No driver. The cores stay at the bootloader's clocks, measured at about 785 MHz (little) and 191 MHz (big), so programs are kept on the little cores |
| Power | Battery and charging | Works | PMI8994 gauge and charger: USB charging tried, limits set to 4.35 V, 1.5 A. The gauge adds 20 s to every start |
| Power | Sleep (suspend) | Untested | |
| Network | USB networking | Works | RNDIS: 172.16.42.1 (the computer gets 172.16.42.2), plus a serial console |
| Network | Wi-Fi | Not working | Not started: QCA6174 on PCIe, which this kernel has no support for on this chip |
| Network | Bluetooth | Not working | QCA6174 on `blsp2_uart2`. Tried by hand: its 3.3 V rail on (PM8994 GPIO 9, which the kernel's device tree leaves off), BT_EN high, 32 kHz clock running; the driver sends and nothing comes back (`command 0xfc00 tx timeout`). The firmware is in Android4Lumia950/firmware-microsoft-talkman |
| Modem | SIM, mobile data, SMS, calls | Not working | Not started: no driver for this chip's modem in this kernel |
| Audio | Speaker, microphone, headphones | Not working | No sound card. Starting the audio DSP by hand with its firmware (`qcadsp8992.mbn`, as `qcadsp8994.mbn`) resets the phone at once, with no crash record; the TAS2552 amp also lacks a supply in the device tree |
| Camera | Rear, 21 MP | Partial | Real pictures; preview about 6 fps. Focus is fixed (no lens driver), and photos are about 5 MP as the sensor's cells are not demosaiced. First pictures looked sharp at table distance |
| Camera | Front, 5 MP | Partial | Real pictures; a clean preview in a lit room, noisy in the dark. Photos about 1.3 MP |
| Camera | Iris camera, flash | Not working | Not started. The iris sensor shares the CSI PHY with the front camera |
| Sensors | Magnetometer | Partial | AK8975: reads through ztOSIAL; no calibration or mounting matrix |
| Sensors | Pressure | Untested | ZPA2326: reads a value |
| Sensors | Ambient light, proximity | Untested | The chip is found and ztOSIAL reads it, but it read 0 in a lit room |
| Sensors | Accelerometer, gyroscope | Not working | MPU-6500 answers `whoami 0x00` |
| Other | FM radio, NFC | Untested | Devices appear |
| Location | GPS | Not working | Depends on the modem |
| Storage | Internal, 32 GB | Works | ztOS takes MainOS and Data; the system fills it on first start |
| Storage | microSD | Untested | |

### Software

| Feature | Status | Notes |
|---|---|---|
| ztMETRO, the shell | Works | 59.8 fps while scrolling Start, measured on a fresh install; 2 late frames in 30 s |
| ztCamera | Partial | Live viewfinder, front and rear switch, photos |
| Android apps (Waydroid) | Untested | With no Wi-Fi, its first-start download has no network |
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

### Good to know when working on it

- The cameras write to physical memory with no IOMMU, as this phone's secure firmware refuses to
  set the camera's IOMMU up, and 256 MB of memory is reserved for them (`cma=256M`).
- `/dev/mem` reads of a camera block whose clocks are off panic the kernel. Only read them while
  a stream is running.
- The full-size sensor readout is more than the camera block's bus takes, so previews are scaled
  on the sensor. `ztcamera-route` holds all of this.
- Kernels hang: test them from RAM with the boot partition empty (see [INSTALL.md](INSTALL.md)).
