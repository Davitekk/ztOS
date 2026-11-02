#!/usr/bin/env python3
"""The Lumia 950's DSI hosts, for a kernel that serves only this phone.

MSM8992 and MSM8994 have the same DSI version (6G, 1.3) at different addresses,
and the tree gives each a row in dsi_cfg_handlers. msm_dsi_cfg_get() searches
from the end, so the MSM8994 row always wins and this phone's hosts fail with
"unable to identify DSI host index". The MSM8992 row goes last.

Usage: patch-dsi-cfg.py <kernel source>
"""
import sys
from pathlib import Path

CFG = "drivers/gpu/drm/msm/dsi/dsi_cfg.c"
ROW = "\t{{MSM_DSI_VER_MAJOR_6G, MSM_DSI_6G_VER_MINOR_V1_3,\n\t\t&{}_dsi_cfg, &msm_dsi_6g_host_ops}},\n"
ORDER = ROW.format("msm8992") + ROW.format("msm8994")
SWAPPED = ROW.format("msm8994") + ROW.format("msm8992")


def main() -> None:
    path = Path(sys.argv[1]) / CFG
    text = path.read_text()
    if text.count(ORDER) != 1:
        sys.exit(f"patch-dsi-cfg: {CFG}: rows not found")
    path.write_text(text.replace(ORDER, SWAPPED))
    print("patch-dsi-cfg: MSM8992's row last")


if __name__ == "__main__":
    main()
