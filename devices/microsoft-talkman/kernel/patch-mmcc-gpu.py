#!/usr/bin/env python3
"""The Lumia 950's GPU power hook: the tree only sets it up on MSM8994.

mmcc-msm8994 hooks the GX power domain so that the GPU's clock source runs at
300 MHz before the domain leaves collapse, as kgsl does. It serves MSM8992 too,
but the hook is behind a test for the MSM8994 compatible, so on this phone
oxili_gfx3d_clk stays stuck off and the GPU fails to power up with -16.

Usage: patch-mmcc-gpu.py <kernel source>
"""
import sys
from pathlib import Path

MMCC = "drivers/clk/qcom/mmcc-msm8994.c"
ANCHOR = (
    '\tif (of_device_is_compatible(pdev->dev.of_node, "qcom,mmcc-msm8994")) {\n'
    "\t\toxili_gfx3d_src = "
)
FIXED = (
    '\tif (of_device_is_compatible(pdev->dev.of_node, "qcom,mmcc-msm8992")) {\n'
    "\t\toxili_gfx3d_src = "
)


def main() -> None:
    path = Path(sys.argv[1]) / MMCC
    text = path.read_text()
    if text.count(ANCHOR) != 1:
        sys.exit(f"patch-mmcc-gpu: {MMCC}: anchor not found once")
    path.write_text(text.replace(ANCHOR, FIXED))
    print("patch-mmcc-gpu: the GPU's power hook on MSM8992")


if __name__ == "__main__":
    main()
