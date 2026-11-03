#!/usr/bin/env python3
"""The Lumia 950's camera button is a button, not a reset.

The tree builds drivers/input/misc/talkman-camera-reboot.c into every kernel: a
debugging aid that restarts the phone on a press of KEY_CAMERA. This takes it out
of the build; the key still reaches userspace through gpio-keys.

Usage: patch-camera-key.py <kernel source>
"""
import sys
from pathlib import Path

MAKEFILE = "drivers/input/misc/Makefile"
LINE = "obj-$(CONFIG_INPUT) += talkman-camera-reboot.o\n"


def main() -> None:
    path = Path(sys.argv[1]) / MAKEFILE
    text = path.read_text()
    if text.count(LINE) != 1:
        sys.exit(f"patch-camera-key: {MAKEFILE}: line not found once")
    path.write_text(text.replace(LINE, ""))
    print("patch-camera-key: no reboot on the camera button")


if __name__ == "__main__":
    main()
