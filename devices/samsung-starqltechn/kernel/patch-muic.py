#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build drivers/s9p-max77705-muic.c into the kernel: the MAX77705's USB-C
MCU (I2C 0x25 on i2c14) switches D+/D- to the AP, which nothing upstream
does, so without it USB stays "not attached" after TWRP. Built in with
MFD_MAX77705 (=y in ztos.config), so the boot stage's rescue gadget sees the
computer too.

Idempotent; takes the kernel source directory as its only argument.
"""
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
here = Path(__file__).resolve().parent
shutil.copy(here / "drivers/s9p-max77705-muic.c", src / "drivers/mfd/s9p-max77705-muic.c")

mk = src / "drivers/mfd/Makefile"
s = mk.read_text()
line = "obj-$(CONFIG_MFD_MAX77705)\t+= s9p-max77705-muic.o\n"
if line not in s:
    anchor = "obj-$(CONFIG_MFD_MAX77705)"
    assert anchor in s, f"{mk}: no MFD_MAX77705 line to put the switch beside"
    mk.write_text(s.rstrip("\n") + "\n" + line)
    print("drivers/mfd: s9p-max77705-muic added")
else:
    print("drivers/mfd: s9p-max77705-muic already there")
