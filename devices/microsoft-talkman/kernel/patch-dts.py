#!/usr/bin/env python3
"""The Lumia 950's device tree edits, for a kernel LK boots.

The tree expects GRUB ("no need for msm-id and friends"), but LK takes an
appended tree by these IDs. They are this phone's, the same in Android4Lumia950's
Android kernel (arch/arm64/boot/dts/mmo/msm8992-mmo-talkman.dts) and in their
lk2nd (msm8992-msft-talkman.dts). 00010000 is an octal literal in both: kept.

The charger: the XL's tree links it to its battery, this one does not, so
qcom-smbchg fails its probe and the phone never charges. The firmware's own
limits for this phone (PmicChargerApp.cfg on EFIESP) are ChgFvMax 4400 mV,
ChgFccMax 3000 mA, ChrgingTermCurrent 200 mA; these stay well inside them:
the XL's 4.35 V, and half a C on this 3000 mAh battery.

Usage: patch-dts.py <kernel source>
"""
import sys
from pathlib import Path

DTS = "arch/arm64/boot/dts/qcom/msm8992-msft-lumia-octagon-talkman.dts"
ANCHOR = '\tcompatible = "microsoft,talkman", "qcom,msm8992";\n'
IDS = (
    "\tqcom,msm-id = <0xfb 00010000 0x0001001a 0>;\n"
    "\tqcom,board-id = <26 0>;\n"
    "\tqcom,pmic-id = <0x20009 0x2000a 0x0 0x0>;\n"
)
BATTERY = "\t\tvoltage-min-design-microvolt = <2800000>;\n"
CHARGE = (
    "\t\tcharge-term-current-microamp = <200000>;\n"
    "\t\tconstant-charge-current-max-microamp = <1500000>;\n"
    "\t\tconstant-charge-voltage-max-microvolt = <4350000>;\n"
)
GAUGE = "&pmi8994_fg {\n"
CHARGER = "&pmi8994_smbchg {\n\tmonitored-battery = <&battery>;\n};\n\n"
OCTAGON = "arch/arm64/boot/dts/qcom/msm8994-msft-lumia-octagon.dtsi"
BOOTARGS = 'bootargs = "earlycon=efifb console=efifb acpi=no";'


def main() -> None:
    path = Path(sys.argv[1]) / DTS
    text = path.read_text()
    for anchor in (ANCHOR, BATTERY, GAUGE):
        if text.count(anchor) != 1:
            sys.exit(f"patch-dts: {DTS}: anchor not found once: {anchor!r}")
    text = text.replace(ANCHOR, ANCHOR + IDS)
    text = text.replace(BATTERY, BATTERY + CHARGE)
    text = text.replace(GAUGE, CHARGER + GAUGE)
    path.write_text(text)

    # (LK appends its command line to this one; there is no EFI framebuffer here)
    path = Path(sys.argv[1]) / OCTAGON
    text = path.read_text()
    if text.count(BOOTARGS) != 1:
        sys.exit(f"patch-dts: {OCTAGON}: anchor not found once: {BOOTARGS!r}")
    path.write_text(text.replace(BOOTARGS, 'bootargs = "acpi=no";'))
    print("patch-dts: LK's IDs and the charger's battery added")


if __name__ == "__main__":
    main()
