#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""btbcm and hci_bcm for the Galaxy S9 (Snapdragon)'s BCM4361 B2.

btbcm: its firmware answers LE Read Transmit Power (0x204b) with one byte and
the host then fails setup with -38 ("unexpected cc 0x204b length: 1 < 3"), as
on the Exynos S9 (bluetooth/patch-btbcm.py): btbcm knows such controllers but
finds them through DMI tables, which an arm64 phone does not have, so the
quirk is set for this board by its device-tree compatible. The speed needs no
patch here: the serdev node's max-speed gives hci_bcm its 3 Mbaud.

hci_bcm: Broadcom chips read their UART CTS_N (our RTS) when BT_REG_ON
rises, and pick autobaud mode when it is asserted. A serdev port is open, RTS
asserted, before hci_bcm powers the chip; Android powers it with the port
closed (its pins pulled high). drive_rts_on_open, hci_bcm's own setting for
the BCM43438/4349, holds RTS deasserted for the power-up, as Android has it;
it is set for this board the same way as the quirk above. (This chip also
answered with RTS asserted, tried from userspace.)

hci_bcm, again: with drive_rts_on_open it raises RTS once the chip is up
and sends the first command (the early baud rate change) at once. This chip
takes no command that soon after RTS first rises: it went unanswered, and
when the chip took the end of it, it answered nothing more ("tx timeout",
"Reset failed -110") until the next power cycle. Tried from userspace on the
same UART: sent at once, 10 of 10 lost; 100 ms after, all answered. 200 ms,
for this board. It can still miss (the start at boot, so far), which
overlay/usr/local/sbin/ztos-starq-bluetooth catches and powers it again.

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

path = Path(sys.argv[1]) / "drivers/bluetooth/hci_bcm.c"
src = path.read_text()
old = ("\t\tif (data->max_speed && bcmdev->oper_speed > data->max_speed)\n"
       "\t\t\tbcmdev->oper_speed = data->max_speed;\n"
       "\t}\n")
new = old + ("\n\t/* ztOS: the BCM4361 powers up with RTS deasserted, as on Android (patch-btbcm.py) */\n"
             "\tif (of_machine_is_compatible(\"samsung,starqltechn\"))\n"
             "\t\tbcmdev->drive_rts_on_open = true;\n")
if new not in src:
    assert src.count(old) == 1, "hci_bcm.c changed: look at drive_rts_on_open again"
    assert "#include <linux/of.h>" in src
    src = src.replace(old, new)
    path.write_text(src)
    print("hci_bcm.c: drive_rts_on_open for samsung,starqltechn")
else:
    print("hci_bcm.c: already patched")

src = path.read_text()
old = ("\t\tif (bcm->dev->drive_rts_on_open)\n"
       "\t\t\thci_uart_set_flow_control(hu, false);\n")
new = old + ("\n\t\t/* ztOS: the BCM4361 takes no command right after RTS rises (patch-btbcm.py) */\n"
             "\t\tif (bcm->dev->drive_rts_on_open && of_machine_is_compatible(\"samsung,starqltechn\"))\n"
             "\t\t\tmsleep(200);\n")
if new not in src:
    assert src.count(old) == 1, "hci_bcm.c changed: look at the wait after RTS again"
    src = src.replace(old, new)
    path.write_text(src)
    print("hci_bcm.c: 200 ms after RTS rises for samsung,starqltechn")
else:
    print("hci_bcm.c: wait after RTS already patched")
