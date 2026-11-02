#!/usr/bin/env python3
"""The Lumia 950's display: two mixers, two ping-pongs, no destination split.

The tree drives this phone's two DSI links with one mixer and ping-pong each
(mdp5_cmd_dual_lm), as on the Lumia 950 XL. Its MSM8992 config also gives the
ping-pong buffer's registers, which turns on destination split: one ping-pong
feeding both links. Both at once left the picture shifted sideways and drifting,
with MDP FIFO underflows and "pp done time out". The XL's config has these two at
0, which leaves the split off.

Usage: patch-mdp5-cfg.py <kernel source>
"""
import sys
from pathlib import Path

CFG = "drivers/gpu/drm/msm/disp/mdp5/mdp5_cfg.c"
PPB = "\t\t.ppb_ctl = 0x334,\n\t\t.ppb_cfg = 0x338,\n"
OFF = "\t\t.ppb_ctl = 0,\n\t\t.ppb_cfg = 0,\n"


def main() -> None:
    path = Path(sys.argv[1]) / CFG
    text = path.read_text()
    if text.count(PPB) != 1:
        sys.exit(f"patch-mdp5-cfg: {CFG}: anchor not found once")
    path.write_text(text.replace(PPB, OFF))
    print("patch-mdp5-cfg: no destination split")


if __name__ == "__main__":
    main()
