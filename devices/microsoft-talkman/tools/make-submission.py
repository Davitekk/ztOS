#!/usr/bin/env python3
"""The device entry, from one place: docs/devices/microsoft-talkman/device.json, and SUBMIT.md
with each field of the form at https://devices.ztos.online/add ready to paste.

Run from the top of the repository, after changing INSTALL.md or anything below.
"""
import json
from pathlib import Path

GUIDE = Path("devices/microsoft-talkman/INSTALL.md").read_text(encoding="utf-8")
SUMMARY = (
    "ztOS on the Snapdragon 808 Lumia 950, booted through BootShim and LK on the phone's own UEFI, "
    "on the Android4Lumia950 mainline kernel (Linux 7.3-rc2). The display, touch, charging and USB "
    "work well, ztMETRO scrolls at about 60 fps on the GPU, and both cameras give pictures. "
    "There is no Wi-Fi, sound or modem yet, and no CPU frequency scaling, so it is an early port "
    "and not yet a usable phone. Tried on one RM-1105."
)
PHONE = {
    "id": "microsoft-talkman",
    "name": "Microsoft Lumia 950",
    "maker": "Microsoft",
    "model": "RM-1105",
    "codename": "talkman",
    "maintainer": "Davitek",
    "contact": "Discord: @davitek_ GitHub: @Davitekk",
}
SPECS = [
    ("SoC", "Qualcomm Snapdragon 808 (MSM8992)"),
    ("CPU", "2× Cortex-A57 and 4× Cortex-A53 (no frequency scaling yet: about 191 and 785 MHz)"),
    ("GPU", "Adreno 418 (freedreno, OpenGL ES 3.0)"),
    ("RAM", "3 GB"),
    ("Storage", "32 GB eMMC, microSD"),
    ("Display", "5.2 in, 1440×2560 AMOLED"),
    ("Battery", "3000 mAh"),
    ("Kernel", "Linux 7.3-rc2 (Android4Lumia950/linux)"),
    ("Released", "2015"),
    ("Device layer", "devices/microsoft-talkman in github.com/Davitekk/ztOS (branch talkman-port)"),
]
W, P, B, U = "working", "partial", "broken", "untested"
FEATURES = [
    ("Boot", "Booting from internal storage", P, "Works, but the power controller does not answer on about half of all starts; the boot stage restarts by itself, so a start can take 2 minutes"),
    ("Display", "Panel", W, "1440x2560 dual-DSI command-mode AMOLED at 60 Hz"),
    ("Display", "Brightness", W, ""),
    ("Display", "GPU", W, "Adreno 418 run as A430, freedreno, GLES 3.0. Scrolling Start measured at 59.8 fps"),
    ("Input", "Touchscreen", W, "Synaptics S3708"),
    ("Input", "Power and volume keys", W, ""),
    ("Input", "Vibration", B, "Not started: no device shows up"),
    ("Power", "CPU, frequency scaling", B, "No driver. The cores stay at the bootloader's clocks, measured at about 785 MHz (little) and 191 MHz (big), so programs are kept on the little cores"),
    ("Power", "Battery and charging", W, "PMI8994 gauge and charger, USB charging tried. The gauge adds 20 s to every start"),
    ("Power", "Sleep (suspend)", U, ""),
    ("Network", "Wi-Fi", B, "Not started: QCA6174 on PCIe, no support on this chip in this kernel"),
    ("Network", "Bluetooth", B, "QCA6174 is found but does not answer on its UART, even with its power rail and enable line on"),
    ("Network", "Mobile data", B, "Not started: no modem driver for this chip in this kernel"),
    ("Network", "USB networking", W, "RNDIS: 172.16.42.1 (the computer gets 172.16.42.2), plus a serial console"),
    ("Modem", "SIM and signal", B, "Not started"),
    ("Modem", "SMS", B, "Not started"),
    ("Modem", "Calls", B, "Not started"),
    ("Audio", "Speaker", B, "No sound card. Starting the audio DSP with its firmware restarts the phone at once"),
    ("Audio", "Microphone", B, "As the speaker"),
    ("Audio", "Headphones", B, "As the speaker"),
    ("Sensors", "Ambient light", U, "The chip is found and ztOSIAL reads it, but it read 0 in a lit room"),
    ("Sensors", "Accelerometer, gyroscope", B, "MPU-6500 answers whoami 0x00"),
    ("Sensors", "Proximity", U, "The chip is found, but it read 0"),
    ("Sensors", "Magnetometer", P, "AK8975 reads through ztOSIAL; no calibration or mounting matrix"),
    ("Sensors", "Pressure", U, "ZPA2326 reads a value"),
    ("Camera", "Rear camera", P, "Real pictures through camss and ccs; preview about 6 fps, fixed focus (no lens driver), photos about 5 MP as the sensor's cells are not demosaiced"),
    ("Camera", "Front camera", P, "Real pictures; a clean preview in a lit room, noisy in the dark. Photos about 1.3 MP"),
    ("Camera", "Iris camera, flash", B, "Not started"),
    ("Location", "GPS", B, "Depends on the modem"),
    ("Software", "ztMETRO", W, "About 60 fps while scrolling"),
    ("Software", "Android apps (Waydroid)", U, "With no Wi-Fi, its first-start download has no network"),
    ("Software", "ztOSIAL (ztos-ial test)", P, "All but one check passed on a fresh install; the one that fails looks for cpufreq clusters"),
]
NOTES = [
    ("It is not usable as a phone yet.", "There is no Wi-Fi, sound or modem. The only network is over the USB cable."),
    ("A start can take 2 minutes with a black screen.", "On about half of all starts the power controller does not answer, and the boot stage restarts by itself. The phone vibrates on each try. Every start also waits 20 s for the battery gauge."),
    ("The phone runs at about half speed.", "With no CPU frequency driver the cores stay at the bootloader's clocks, and heavy apps feel it."),
    ("The cameras' colour is approximate and focus is fixed.", "There is no ISP: the picture is made on the CPU, with no calibration for these sensors, and no driver for the lens."),
    ("Do not press both volume keys in LK.", "That enters emergency download mode."),
    ("Never write the DPP partition.", "It holds calibration that cannot be had back. The install scripts leave it alone."),
]


def device_json():
    return {
        **PHONE, "added": "", "summary": SUMMARY, "photo": "photo.jpg", "photo_caption": "",
        "specs": [list(s) for s in SPECS],
        "install": {"markdown": GUIDE},
        "features": [{"category": c, "feature": f, "status": s, "notes": n} for c, f, s, n in FEATURES],
        "notes": [{"title": t, "text": x} for t, x in NOTES],
    }


def submit_md():
    fence = "`" * 4
    lines = [
        "# The form at https://devices.ztos.online/add, field by field",
        "",
        "Generated by `tools/make-submission.py`. Moderators read every entry before it appears.",
        "",
        "**You still need to do two things yourself:** take a photo of the phone running ztOS for the",
        "Photo field (nobody else can), and press Send.",
        "",
        "## The phone",
        "",
    ]
    for key, label in (("name", "Name"), ("maker", "Maker"), ("model", "Model number"), ("codename", "Codename"),
                       ("maintainer", "Your name"), ("contact", "Discord name, GitHub or link")):
        lines.append(f"- **{label}:** `{PHONE[key]}`")
    lines += ["", f"## About this port ({len(SUMMARY)} of 800 characters)", "", fence, SUMMARY, fence, "",
              "## Specifications", "", "| | |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in SPECS]
    lines += ["", "## What works", "", "The form starts with a list of features: set each one as below, and use",
              "\"Add a feature\" for those it does not list.", "", "| Category | Feature | Status | Notes |", "|---|---|---|---|"]
    lines += [f"| {c} | {f} | {s} | {n} |" for c, f, s, n in FEATURES]
    lines += ["", "## Known quirks", ""]
    for title, text in NOTES:
        lines += [f"- **{title}** {text}"]
    lines += ["", f"## Installation guide ({len(GUIDE)} of 30000 characters)", "",
              "Paste everything between the two fences:", "", fence, GUIDE.rstrip(), fence, ""]
    return "\n".join(lines)


def main():
    assert len(SUMMARY) <= 800, len(SUMMARY)
    assert len(GUIDE) <= 30000, len(GUIDE)
    out = Path("docs/devices/microsoft-talkman")
    out.mkdir(parents=True, exist_ok=True)
    (out / "device.json").write_text(json.dumps(device_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    Path("devices/microsoft-talkman/SUBMIT.md").write_text(submit_md(), encoding="utf-8", newline="\n")
    print(f"summary {len(SUMMARY)}/800, guide {len(GUIDE)}/30000, {len(FEATURES)} features")


if __name__ == "__main__":
    main()
