#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""btbcm for the Galaxy S9 (Snapdragon)'s BCM4361 B2.

Its firmware answers LE Read Transmit Power (0x204b) with one byte and the
host then fails setup with -38 ("unexpected cc 0x204b length: 1 < 3"), as on
the Exynos S9 (bluetooth/patch-btbcm.py): btbcm knows such controllers but
finds them through DMI tables, which an arm64 phone does not have, so the
quirk is set for this board by its device-tree compatible. The speed needs no
patch here: the serdev node's max-speed gives hci_bcm its 3 Mbaud.

Asserted, so a changed upstream file fails instead of silently building
without it. Takes the kernel source directory as its only argument.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "drivers/bluetooth/btbcm.c"
src = path.read_text()
old = "\tif (dmi_first_match(disable_broken_read_transmit_power))\n"
new = ("\tif (dmi_first_match(disable_broken_read_transmit_power) ||\n"
       "\t    of_machine_is_compatible(\"samsung,starqltechn\"))\n")
if new not in src:
    assert src.count(old) == 1, "btbcm.c changed: look at the quirk again"
    src = src.replace(old, new)
    if "#include <linux/of.h>" not in src:
        src = src.replace("#include <linux/module.h>\n", "#include <linux/module.h>\n#include <linux/of.h>\n", 1)
    path.write_text(src)
    print("btbcm.c: broken LE Read Transmit Power quirk for samsung,starqltechn")
else:
    print("btbcm.c: already patched")
