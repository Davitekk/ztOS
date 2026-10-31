#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""The WCD9340 codec: decimator 8 can take a digital mic.

Each decimator has a switch between the analog (ADC) and the digital (DMIC)
side, bit 7 of its CDC_TXn_TX_PATH_CFG0, which wcd934x_dec_enum_put() sets
from the "ADC MUXn" control. "ADC MUX8" sits in ADC_MUX1_CFG1 at shift 4
(tx_adc_mux8_enum), but the function looks for decimator 8 under ADC_MUX0_CFG1
only: for ADC MUX8 it finds no register and never sets the bit, so TX8
stayed on the analog side (TX8_TX_PATH_CFG0 0x50 on the S9, whose top mic,
DMIC2, goes through DEC8). Now ADC_MUX1_CFG1 shift 4 is TX8 too (0xd0).
(Not all the S9's mics need: they still give silence; see README.)

Asserted, so a changed upstream file fails instead of silently building
without it. Takes the kernel source directory as its only argument.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "sound/soc/codecs/wcd934x.c"
src = path.read_text()
# the enum this is about, as it is
assert ("tx_adc_mux8_enum =\n\tSOC_ENUM_SINGLE(WCD934X_CDC_TX_INP_MUX_ADC_MUX1_CFG1, 4,") in src, \
    "wcd934x.c: ADC MUX8 moved: look again"
old = ("\tcase WCD934X_CDC_TX_INP_MUX_ADC_MUX1_CFG1:\n"
       "\t\tif (e->shift_l == 0)\n"
       "\t\t\tmic_sel_reg = WCD934X_CDC_TX1_TX_PATH_CFG0;\n"
       "\t\telse if (e->shift_l == 2)\n"
       "\t\t\tmic_sel_reg = WCD934X_CDC_TX5_TX_PATH_CFG0;\n"
       "\t\tbreak;\n")
new = ("\tcase WCD934X_CDC_TX_INP_MUX_ADC_MUX1_CFG1:\n"
       "\t\tif (e->shift_l == 0)\n"
       "\t\t\tmic_sel_reg = WCD934X_CDC_TX1_TX_PATH_CFG0;\n"
       "\t\telse if (e->shift_l == 2)\n"
       "\t\t\tmic_sel_reg = WCD934X_CDC_TX5_TX_PATH_CFG0;\n"
       "\t\telse if (e->shift_l == 4)\t/* ztOS: ADC MUX8 (patch-wcd934x.py) */\n"
       "\t\t\tmic_sel_reg = WCD934X_CDC_TX8_TX_PATH_CFG0;\n"
       "\t\tbreak;\n")
if new not in src:
    assert src.count(old) == 1, "wcd934x.c changed: look at wcd934x_dec_enum_put again"
    path.write_text(src.replace(old, new))
    print("wcd934x.c: ADC MUX8 sets decimator 8's DMIC switch")
else:
    print("wcd934x.c: already patched")
