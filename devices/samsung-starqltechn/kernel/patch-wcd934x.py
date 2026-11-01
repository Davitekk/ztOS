#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""The WCD9340 codec on the Galaxy S9 (Snapdragon): two fixes.

1. Decimator 8 can take a digital mic. Each decimator has a switch between
   the analog (ADC) and the digital (DMIC) side, bit 7 of its
   CDC_TXn_TX_PATH_CFG0, which wcd934x_dec_enum_put() sets from the "ADC
   MUXn" control. "ADC MUX8" sits in ADC_MUX1_CFG1 at shift 4
   (tx_adc_mux8_enum), but the function looks for decimator 8 under
   ADC_MUX0_CFG1 only: for ADC MUX8 it finds no register and never sets the
   bit, so TX8 stayed on the analog side (TX8_TX_PATH_CFG0 0x50; the S9's top
   mic, DMIC2, goes through DEC8). Now ADC_MUX1_CFG1 shift 4 is TX8 too.

2. Qualcomm's register defaults, at init. Qualcomm's tavil driver (Samsung's
   S9 kernel has it unchanged) writes two tables at every start,
   tavil_codec_reg_defaults[] and tavil_codec_reg_init_common_val[]; mainline
   writes three of their values. Among the rest: the mic bias regulators'
   test registers (MICBn_TEST_CTL_1 0xfa, MICB1_TEST_CTL_2), a clock gate
   (CODEC_RPM_CLK_GATE bit 3, set on this phone, cleared by Qualcomm) and an
   MCLK option (CODEC_RPM_CLK_MCLK_CFG bit 2). With mic bias at 1.8 V and the
   DMIC clock at 2.4 MHz as Samsung's service manual wants them, both phone
   mics still delivered only zeros. Both tables are applied here, for this
   board, except the two CPR voltages (written by another mechanism there)
   and what mainline already sets; addresses from Qualcomm's
   wcd934x_registers.h, as mainline's header has not all the names.

Asserted, so a changed upstream file fails instead of silently building
without it. Takes the kernel source directory as its only argument.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "sound/soc/codecs/wcd934x.c"
src = path.read_text()

# 1 ------------------------------------------------------------------------
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
    src = src.replace(old, new)
    print("wcd934x.c: ADC MUX8 sets decimator 8's DMIC switch")

# 2 ------------------------------------------------------------------------
# {register, mask, value}, in Qualcomm's order (reg_defaults, then
# reg_init_common_val), with Qualcomm's names
QCOM_INIT = [
    (0x0629, 0xff, 0x75, "BIAS_VBG_FINE_ADJ"),
    (0x0b53, 0x01, 0x01, "CDC_RX0_RX_PATH_DSMDEM_CTL"),
    (0x0b67, 0x01, 0x01, "CDC_RX1_RX_PATH_DSMDEM_CTL"),
    (0x0b7b, 0x01, 0x01, "CDC_RX2_RX_PATH_DSMDEM_CTL"),
    (0x0b8f, 0x01, 0x01, "CDC_RX3_RX_PATH_DSMDEM_CTL"),
    (0x0ba3, 0x01, 0x01, "CDC_RX4_RX_PATH_DSMDEM_CTL"),
    (0x0bdf, 0x01, 0x01, "CDC_RX7_RX_PATH_DSMDEM_CTL"),
    (0x0bf3, 0x01, 0x01, "CDC_RX8_RX_PATH_DSMDEM_CTL"),
    (0x0b40, 0x1e, 0x18, "CDC_COMPANDER8_CTL7"),
    (0x0b38, 0x1e, 0x18, "CDC_COMPANDER7_CTL7"),
    (0x0b49, 0x08, 0x00, "CDC_RX0_RX_PATH_SEC0"),
    (0x0c03, 0x03, 0x00, "CDC_CLSH_DECAY_CTRL"),
    (0x066c, 0x07, 0x01, "MICB1_TEST_CTL_2"),
    (0x0c1b, 0x3f, 0x12, "CDC_BOOST0_BOOST_CFG1"),
    (0x0c1c, 0x1c, 0x08, "CDC_BOOST0_BOOST_CFG2"),
    (0x0c23, 0x3f, 0x12, "CDC_BOOST1_BOOST_CFG1"),
    (0x0c24, 0x1c, 0x08, "CDC_BOOST1_BOOST_CFG2"),
    (0x0213, 0x1f, 0x09, "CPE_SS_CPARMAD_BUFRDY_INT_PERIOD"),
    (0x0a33, 0x01, 0x00, "CDC_TX0_TX_PATH_CFG1"),
    (0x0a43, 0x01, 0x00, "CDC_TX1_TX_PATH_CFG1"),
    (0x0a53, 0x01, 0x00, "CDC_TX2_TX_PATH_CFG1"),
    (0x0a63, 0x01, 0x00, "CDC_TX3_TX_PATH_CFG1"),
    (0x0a73, 0x01, 0x00, "CDC_TX4_TX_PATH_CFG1"),
    (0x0a83, 0x01, 0x00, "CDC_TX5_TX_PATH_CFG1"),
    (0x0a93, 0x01, 0x00, "CDC_TX6_TX_PATH_CFG1"),
    (0x0aa3, 0x01, 0x00, "CDC_TX7_TX_PATH_CFG1"),
    (0x0ab3, 0x01, 0x00, "CDC_TX8_TX_PATH_CFG1"),
    (0x06b6, 0x0f, 0x02, "RX_OCP_CTL"),
    (0x06ce, 0xff, 0x3a, "HPH_OCP_CTL"),
    (0x06d4, 0x01, 0x01, "HPH_L_TEST"),
    (0x06d7, 0x01, 0x01, "HPH_R_TEST"),
    (0x0111, 0xff, 0x20, "CPE_FLL_CONFIG_CTL_2"),
    (0x0721, 0x0c, 0x00, "MBHC_NEW_CTL_2"),
    (0x0003, 0x04, 0x04, "CODEC_RPM_CLK_MCLK_CFG"),
    (0x0c0a, 0x0f, 0x00, "CDC_CLSH_K2_MSB"),
    (0x0c0b, 0xff, 0x60, "CDC_CLSH_K2_LSB"),
    (0x0c1a, 0x7c, 0x58, "CDC_BOOST0_BOOST_CTL"),
    (0x0c22, 0x7c, 0x58, "CDC_BOOST1_BOOST_CTL"),
    (0x0d82, 0x02, 0x02, "CDC_TOP_TOP_CFG1"),
    (0x0d82, 0x01, 0x01, "CDC_TOP_TOP_CFG1"),
    (0x0ac3, 0x01, 0x01, "CDC_TX9_SPKR_PROT_PATH_CFG0"),
    (0x0ac7, 0x01, 0x01, "CDC_TX10_SPKR_PROT_PATH_CFG0"),
    (0x0acb, 0x01, 0x01, "CDC_TX11_SPKR_PROT_PATH_CFG0"),
    (0x0acf, 0x01, 0x01, "CDC_TX12_SPKR_PROT_PATH_CFG0"),
    (0x006c, 0x01, 0x01, "DATA_HUB_SB_TX11_INP_CFG"),
    (0x0d42, 0x01, 0x01, "CDC_CLK_RST_CTRL_FS_CNT_CONTROL"),
    (0x0b34, 0x80, 0x80, "CDC_COMPANDER7_CTL3"),
    (0x0b3c, 0x80, 0x80, "CDC_COMPANDER8_CTL3"),
    (0x0b38, 0x01, 0x01, "CDC_COMPANDER7_CTL7"),
    (0x0b40, 0x01, 0x01, "CDC_COMPANDER8_CTL7"),
    (0x0002, 0x08, 0x00, "CODEC_RPM_CLK_GATE"),
    (0x8019, 0xff, 0x0a, "TLMM_DMIC3_CLK_PINCFG"),
    (0x801a, 0xff, 0x0a, "TLMM_DMIC3_DATA_PINCFG"),
    (0x0214, 0x60, 0x00, "CPE_SS_SVA_CFG"),
    (0x021c, 0x10, 0x10, "CPE_SS_CPAR_CFG"),
    (0x066b, 0xff, 0xfa, "MICB1_TEST_CTL_1"),
    (0x066e, 0xff, 0xfa, "MICB2_TEST_CTL_1"),
    (0x0671, 0xff, 0xfa, "MICB3_TEST_CTL_1"),
    (0x0674, 0xff, 0xfa, "MICB4_TEST_CTL_1"),
    (0x0a3e, 0xff, 0x4d, "CDC_TX0_TX_PATH_SEC7"),
]
table = "".join(f"\t\t{{ 0x{r:04x}, 0x{m:02x}, 0x{v:02x} }},\t/* {n} */\n" for r, m, v, n in QCOM_INIT)
old = ("\t/* Take DMICs out of reset */\n"
       "\tregmap_update_bits(rm, WCD934X_CPE_SS_DMIC_CFG, 0x80, 0x00);\n"
       "}\n")
new = ("\t/* Take DMICs out of reset */\n"
       "\tregmap_update_bits(rm, WCD934X_CPE_SS_DMIC_CFG, 0x80, 0x00);\n"
       "\n"
       "\t/* ztOS: Qualcomm's register defaults (tavil_codec_reg_defaults and\n"
       "\t * _reg_init_common_val), without the CPR voltages (patch-wcd934x.py) */\n"
       "\tif (of_machine_is_compatible(\"samsung,starqltechn\")) {\n"
       "\t\tstatic const struct { u16 reg; u8 mask, val; } qcom_init[] = {\n"
       + table +
       "\t\t};\n"
       "\t\tint i;\n"
       "\n"
       "\t\tfor (i = 0; i < ARRAY_SIZE(qcom_init); i++)\n"
       "\t\t\tregmap_update_bits(rm, qcom_init[i].reg, qcom_init[i].mask,\n"
       "\t\t\t\t\t   qcom_init[i].val);\n"
       "\t}\n"
       "}\n")
if "ztOS: Qualcomm's register defaults" not in src:
    assert src.count(old) == 1, "wcd934x.c changed: look at wcd934x_hw_init again"
    assert "#include <linux/of.h>" in src
    src = src.replace(old, new)
    print(f"wcd934x.c: Qualcomm's {len(QCOM_INIT)} register defaults at init for samsung,starqltechn")

path.write_text(src)
