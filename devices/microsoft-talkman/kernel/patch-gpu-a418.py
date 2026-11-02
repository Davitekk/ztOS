#!/usr/bin/env python3
"""The Lumia 950's Adreno 418, run as the A430 the tree knows.

The tree's device tree says A430 (the MSM8994's GPU) for this phone too. Android's
kernel for this phone (kgsl: adreno-gpulist.h, adreno_a4xx.c, msm8992-gpu.dtsi)
says chip 4.1.8, the same a420 firmware, and treats it as an A430 for its VBIF
settings, its SP/TP power switch and its register layout, so that stays. Two
things don't, for this phone:

- Its GMEM is 512 KiB, not the A430's 1.5 MiB: all the OCMEM this SoC gives it.
- The tree's A430 power and address space fixes run only on the MSM8994 machine
  compatible, though the SoC's GPU, its SMMU and TrustZone's handling of it are
  the same here. Without them the GPU's power domain stays off: oxili_gfx3d_clk
  is stuck and the GPU fails to power up with -16.

Usage: patch-gpu-a418.py <kernel source>
"""
import sys
from pathlib import Path

MACHINE_8994 = 'of_machine_is_compatible("qcom,msm8994")'
MACHINE_8992 = 'of_machine_is_compatible("qcom,msm8992")'
GUARDS = {
    "drivers/gpu/drm/msm/adreno/adreno_device.c": 2,
    "drivers/gpu/drm/msm/adreno/adreno_gpu.c": 1,
}
CATALOG = "drivers/gpu/drm/msm/adreno/a4xx_catalog.c"
A430 = ".chip_ids = ADRENO_CHIP_IDS(0x04030000, 0x04030002),"
GMEM = ".gmem  = (SZ_1M + SZ_512K),"
GMEM_418 = ".gmem  = SZ_512K,"


def main() -> None:
    src = Path(sys.argv[1])
    for name, count in GUARDS.items():
        path = src / name
        text = path.read_text()
        if text.count(MACHINE_8994) != count:
            sys.exit(f"patch-gpu-a418: {name}: expected {count} MSM8994 checks")
        path.write_text(text.replace(MACHINE_8994, MACHINE_8992))

    path = src / CATALOG
    text = path.read_text()
    start = text.find(A430)
    if start < 0 or text.count(A430) != 1:
        sys.exit(f"patch-gpu-a418: {CATALOG}: A430 row not found once")
    gmem = text.find(GMEM, start)
    if gmem < 0:
        sys.exit(f"patch-gpu-a418: {CATALOG}: A430's GMEM not found")
    path.write_text(text[:gmem] + GMEM_418 + text[gmem + len(GMEM):])
    print("patch-gpu-a418: 512 KiB GMEM, the A430 fixes on MSM8992")


if __name__ == "__main__":
    main()
