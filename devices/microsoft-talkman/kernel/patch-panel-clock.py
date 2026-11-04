#!/usr/bin/env python3
"""The Lumia 950's panel: the DSI link at the speed Android's timings give it.

On this command-mode panel the mode's clock sets how fast a frame is sent, not the
refresh rate, which comes from clock / (htotal * vtotal). At the tree's 240981 kHz each
side's link runs at 723 Mbps and a frame takes about 15.3 ms of its 16.7 ms, so a commit
has about 1.3 ms from the end of one transfer to the start of the next; miss it and the
frame shows 16.7 ms late. Android's timings for this panel come to 780 Mbps. Horizontal
blanking is not sent in command mode, so a longer front porch keeps the mode at 60 Hz.

Usage: patch-panel-clock.py <kernel source>
"""
import sys
from pathlib import Path

PANEL = "drivers/gpu/drm/panel/panel-samsung-ams567dj06.c"
WAS = """	.clock = 240981,
	.hdisplay = 1440,
	.hsync_start = 1440 + 76,
	.hsync_end = 1440 + 76 + 16,
	.htotal = 1440 + 76 + 16 + 32,
"""
NOW = """	.clock = 259934,
	.hdisplay = 1440,
	.hsync_start = 1440 + 199,
	.hsync_end = 1440 + 199 + 16,
	.htotal = 1440 + 199 + 16 + 32,
"""


def main() -> None:
    path = Path(sys.argv[1]) / PANEL
    text = path.read_text()
    if text.count(WAS) != 1:
        sys.exit(f"patch-panel-clock: {PANEL}: mode not found once")
    path.write_text(text.replace(WAS, NOW))
    print("patch-panel-clock: DSI at 780 Mbps, still 60 Hz")


if __name__ == "__main__":
    main()
