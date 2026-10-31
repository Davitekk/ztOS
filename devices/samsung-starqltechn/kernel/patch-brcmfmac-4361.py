#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""brcmfmac for the BCM4361 B2 (the Galaxy S9's Wi-Fi, Murata module on the
SCV38 / SM-G9600): chip and PCIe IDs, the 0x170000 RAM base, a deferred probe
for a chip that is not ready yet, and DHD-style stamping of host-to-dongle
work items, which this firmware checks.

Taken unchanged from the Galaxy S9+ mainline port's scripts/build/patch_tree.py
(github.com/SheroAbi/galaxy-s9plus-mainline-linux, GPL-2.0, commit bcee6014),
which carries Markuss Broks's upstream brcmfmac patch: the chip is the same on
the Exynos and the Snapdragon phones, only the PCIe host differs.

Idempotent; takes the kernel source directory as its only argument, and fails
loudly if an upstream change moves anything it edits.
"""
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])

# --- brcmfmac: BCM4361 (WiFi of this phone) ----------------------------------
# Markuss Broks's upstream patch (wireless-next v3, 2026-08-20), plus the two
# extra BRCMF_PCIE_DEVICE lines maintainer Arend van Spriel asked for in
# review (2G-only 0x4420 and 5G-only 0x4421 variants). Chip rambase and
# sr_capable like the 4359, per the patch's chip.c hunk. Every insert is
# guarded on its own so a partial application never blocks a build.
hw_ids = "drivers/net/wireless/broadcom/brcm80211/include/brcm_hw_ids.h"
hw_path = src / hw_ids
hw = hw_path.read_text()
changed = False
if "BRCM_CC_4361_CHIP_ID" not in hw:
    anchor = "#define BRCM_CC_4359_CHIP_ID\t\t0x4359\n"
    assert anchor in hw, f"{hw_ids}: 4359 chip anchor not found"
    hw = hw.replace(anchor, anchor +
        "#define BRCM_CC_4361_CHIP_ID\t\t0x4361\n", 1)
    changed = True
if "BRCM_PCIE_4361_DEVICE_ID" not in hw:
    anchor = "#define BRCM_PCIE_4359_DEVICE_ID\t0x43ef\n"
    assert anchor in hw, f"{hw_ids}: 4359 device id anchor not found"
    hw = hw.replace(anchor, anchor +
        "#define BRCM_PCIE_4361_DEVICE_ID\t\t0x441f\n"
        "#define BRCM_PCIE_4361_2G_DEVICE_ID\t0x4420\n"
        "#define BRCM_PCIE_4361_5G_DEVICE_ID\t0x4421\n", 1)
    changed = True
if changed:
    hw_path.write_text(hw)
    print(f"{hw_ids}: 4361 IDs added")
else:
    print(f"{hw_ids}: 4361 already there")

pcie_c = "drivers/net/wireless/broadcom/brcm80211/brcmfmac/pcie.c"
pc_path = src / pcie_c
pc = pc_path.read_text()
pc_changed = False
if 'BRCMF_FW_CLM_DEF(4361' not in pc:
    anchor = 'BRCMF_FW_DEF(4359, "brcmfmac4359-pcie");'
    assert anchor in pc, f"{pcie_c}: 4359 fw anchor not found"
    pc = pc.replace(anchor, anchor +
        '\nBRCMF_FW_CLM_DEF(4361, "brcmfmac4361-pcie");', 1)
    pc_changed = True
if "BRCMF_FW_ENTRY(BRCM_CC_4361_CHIP_ID" not in pc:
    anchor = "\tBRCMF_FW_ENTRY(BRCM_CC_4359_CHIP_ID, 0x000001FF, 4359),"
    assert anchor in pc, f"{pcie_c}: 4359 fw entry anchor not found"
    pc = pc.replace(anchor, anchor +
        "\n\tBRCMF_FW_ENTRY(BRCM_CC_4361_CHIP_ID, 0xFFFFFFFF, 4361),", 1)
    pc_changed = True
if "BRCM_PCIE_4361_DEVICE_ID, WCC" not in pc:
    anchor = "\tBRCMF_PCIE_DEVICE(BRCM_PCIE_4359_DEVICE_ID, WCC),"
    assert anchor in pc, f"{pcie_c}: 4359 device anchor not found"
    pc = pc.replace(anchor, anchor +
        "\n\tBRCMF_PCIE_DEVICE(BRCM_PCIE_4361_DEVICE_ID, WCC),"
        "\n\tBRCMF_PCIE_DEVICE(BRCM_PCIE_4361_2G_DEVICE_ID, WCC),"
        "\n\tBRCMF_PCIE_DEVICE(BRCM_PCIE_4361_5G_DEVICE_ID, WCC),", 1)
    pc_changed = True
# A cold-started chip can enumerate and still answer its first BAR read with
# all ones (chip_recognition "MMIO read failed" -> -ENODEV) when the host
# gets to it too early. Deferring the probe lets the driver core try again
# later in the boot instead of giving up on the only WLAN there is.
if "brcmf_pcie_probe: defer" not in pc:
    anchor = ("\t\tret = PTR_ERR(devinfo->ci);\n"
              "\t\tdevinfo->ci = NULL;\n"
              "\t\tgoto fail;\n")
    assert anchor in pc, f"{pcie_c}: chip_attach failure anchor not found"
    pc = pc.replace(anchor,
        "\t\tret = PTR_ERR(devinfo->ci);\n"
        "\t\tif (ret == -ENODEV)\t/* brcmf_pcie_probe: defer, chip not ready yet */\n"
        "\t\t\tret = -EPROBE_DEFER;\n"
        "\t\tdevinfo->ci = NULL;\n"
        "\t\tgoto fail;\n", 1)
    pc_changed = True
if pc_changed:
    pc_path.write_text(pc)
    print(f"{pcie_c}: 4361 support added")
else:
    print(f"{pcie_c}: 4361 already there")

chip_c = "drivers/net/wireless/broadcom/brcm80211/brcmfmac/chip.c"
ch_path = src / chip_c
ch = ch_path.read_text()
ch_orig = ch
case_4359 = "case BRCM_CC_4359_CHIP_ID:"
case_4361 = "case BRCM_CC_4361_CHIP_ID:"
# tcm_rambase(): the vendor driver files the 4361 under the 4347 chip class
# (bcmdhd siutils.c) and loads it at CR4_4347_RAM_BASE = 0x170000
# (dhd_pcie.c) -- not at the 4359's rev-dependent 0x180000/0x160000 that the
# upstream patch used. 64 KB off is exactly "FW failed to initialize" with
# nothing else to show. Any earlier placement in the function is undone
# first, so the edit is idempotent.
head, sep, tail = ch.partition("static u32 brcmf_chip_tcm_rambase(")
assert sep, f"{chip_c}: tcm_rambase not found"
fn_end = tail.index("\n}\n")
fn, rest = tail[:fn_end], tail[fn_end:]
fn = re.sub(r"\tcase BRCM_CC_4361_CHIP_ID:[^\n]*\n", "", fn)
anchor = "\tcase BRCM_CC_43751_CHIP_ID:\n"
assert anchor in fn, f"{chip_c}: 43751 rambase anchor not found"
fn = fn.replace(anchor,
                "\t" + case_4361 + "\t/* 4347 class: CR4_4347_RAM_BASE */\n"
                + anchor, 1)
ch = head + sep + fn + rest
# sr_capable(): the retention_ctl check, like the 4359 (last occurrence).
idx = ch.rfind(case_4359)
assert idx >= 0
fn_start = ch.rfind("bool brcmf_chip_sr_capable(", 0, idx)
if case_4361 not in ch[fn_start:idx]:
    ch = ch[:idx] + case_4361 + "\n\t" + ch[idx:]
ch = ch.replace(case_4361 + "\n\t\t" + case_4359, case_4361 + "\n\t" + case_4359)
if ch != ch_orig:
    ch_path.write_text(ch)
    print(f"{chip_c}: 4361 rambase 0x170000 / sr_capable set")
else:
    print(f"{chip_c}: 4361 already there")

# --- brcmfmac: stamp H2D work items like Broadcom's DHD does -----------------
# Every host-to-dongle ring item carries a per-ring sequence number in the
# common header's 4th byte (DHD: cmn_msg_hdr_t.epoch = seqnum % 253, seqnum
# starting at 254) and a phase bit (flags bit 7, flipped whenever an
# allocation lands on the ring base). brcmfmac leaves both at zero. The
# BCM4361 B2 firmware verifies them: every unstamped item on the control
# ring came back as ring status BADOPTION (3) and the first ioctl timed out.
# Stamping happens centrally in brcmf_commonring_write_complete(), after the
# callers filled their headers; D2H rings are never written by the host, so
# only H2D rings are touched. Firmware that does not check ignores the bytes.
cr_h = "drivers/net/wireless/broadcom/brcm80211/brcmfmac/commonring.h"
cr_h_path = src / cr_h
crh = cr_h_path.read_text()
if "stamp_ptr" not in crh:
    anchor = "\tbool was_full;\n"
    assert anchor in crh, f"{cr_h}: was_full anchor not found"
    crh = crh.replace(anchor, anchor +
        "\n\t/* H2D item stamping: next unstamped item, phase bit, sequence */\n"
        "\tu16 stamp_ptr;\n"
        "\tu8 phase;\n"
        "\tu32 seqnum;\n", 1)
    cr_h_path.write_text(crh)
    print(f"{cr_h}: stamp fields added")
else:
    print(f"{cr_h}: stamp fields already there")

cr_c = "drivers/net/wireless/broadcom/brcm80211/brcmfmac/commonring.c"
cr_c_path = src / cr_c
crc = cr_c_path.read_text()
if "brcmf_commonring_stamp" not in crc:
    anchor = "void brcmf_commonring_config(struct brcmf_commonring *commonring, u16 depth,"
    assert anchor in crc, f"{cr_c}: config anchor not found"
    helper = (
        "/*\n"
        " * Every host-to-dongle work item carries a per-ring sequence number in\n"
        " * the common header's 4th byte (\"epoch\") and a phase bit in the flags\n"
        " * byte, the way Broadcom's DHD stamps them: epoch = seqnum % 253 with\n"
        " * seqnum starting at 254, phase (bit 7) flipped whenever an allocation\n"
        " * lands on the ring base. Firmware that verifies them (BCM4361 B2)\n"
        " * rejects unstamped items with ring status BADOPTION.\n"
        " */\n"
        "#define BRCMF_H2D_EPOCH_MODULO\t253\n"
        "#define BRCMF_H2D_EPOCH_INIT\t(BRCMF_H2D_EPOCH_MODULO + 1)\n"
        "#define BRCMF_H2D_PHASE_BIT\t0x80\n"
        "\n"
        "static void brcmf_commonring_stamp(struct brcmf_commonring *commonring)\n"
        "{\n"
        "\tu8 *item;\n"
        "\n"
        "\twhile (commonring->stamp_ptr != commonring->w_ptr) {\n"
        "\t\tif (commonring->stamp_ptr == 0)\n"
        "\t\t\tcommonring->phase ^= BRCMF_H2D_PHASE_BIT;\n"
        "\t\titem = commonring->buf_addr +\n"
        "\t\t       commonring->stamp_ptr * commonring->item_len;\n"
        "\t\titem[2] = (item[2] & ~BRCMF_H2D_PHASE_BIT) | commonring->phase;\n"
        "\t\titem[3] = commonring->seqnum % BRCMF_H2D_EPOCH_MODULO;\n"
        "\t\tcommonring->seqnum++;\n"
        "\t\tcommonring->stamp_ptr++;\n"
        "\t\tif (commonring->stamp_ptr == commonring->depth)\n"
        "\t\t\tcommonring->stamp_ptr = 0;\n"
        "\t}\n"
        "}\n"
        "\n"
    )
    crc = crc.replace(anchor, helper + anchor, 1)
    anchor = "\tcommonring->f_ptr = 0;\n}\n"
    assert anchor in crc, f"{cr_c}: config f_ptr anchor not found"
    crc = crc.replace(anchor,
        "\tcommonring->f_ptr = 0;\n"
        "\tcommonring->stamp_ptr = 0;\n"
        "\tcommonring->phase = 0;\n"
        "\tcommonring->seqnum = BRCMF_H2D_EPOCH_INIT;\n"
        "}\n", 1)
    anchor = "int brcmf_commonring_write_complete(struct brcmf_commonring *commonring)\n{\n"
    assert anchor in crc, f"{cr_c}: write_complete anchor not found"
    crc = crc.replace(anchor, anchor + "\tbrcmf_commonring_stamp(commonring);\n\n", 1)
    cr_c_path.write_text(crc)
    print(f"{cr_c}: H2D item stamping added")
else:
    print(f"{cr_c}: H2D item stamping already there")

