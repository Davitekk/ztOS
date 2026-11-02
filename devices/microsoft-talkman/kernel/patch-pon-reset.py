#!/usr/bin/env python3
"""Every reboot of the Lumia 950 is a full reset of its PMIC.

The PMIC's power-on default for a PS_HOLD reset leaves the RPM running. After
such a warm reboot the RPM's SMD channel stays in the state the last kernel left,
and the next kernel's requests time out (clk-smd-rpm -110, "failed to sync cx"):
no regulators, so no touchscreen, display or SD card. A press of the power button
has always been a full reset, which is why only that boot worked.

The registers, values and order are qpnp_pon_reset_config() in the phone's Android
kernel (Android4Lumia950/android_kernel_mmo_msm8994, drivers/platform/msm/
qpnp-power-on.c): PS_HOLD_RST_CTL 0x5a with PON_POWER_OFF_HARD_RESET 0x07, with
the reset's enable, bit 7 of PS_HOLD_RST_CTL2 0x5b, off around the change and three
sleep clock cycles (94 us at 32 kHz) after turning it off.

Usage: patch-pon-reset.py <kernel source>
"""
import sys
from pathlib import Path

PON = "drivers/power/reset/qcom-pon.c"
DEFINE = "#define PON_SOFT_RB_SPARE\t\t0x8f\n"
ADD_DEFINE = """#define PON_PS_HOLD_RST_CTL\t\t0x5a
#define PON_PS_HOLD_RST_CTL2\t\t0x5b
#define PON_PS_HOLD_RST_EN\t\tBIT(7)
#define PON_PS_HOLD_TYPE_MASK\t\tGENMASK(3, 0)
#define PON_PS_HOLD_HARD_RESET\t\t0x07
"""
PROBE = "static int qcom_pon_probe(struct platform_device *pdev)\n"
ADD_FUNC = """static int qcom_pon_set_hard_reset(struct qcom_pon *pon)
{
	u32 ctl = pon->baseaddr + PON_PS_HOLD_RST_CTL;
	u32 ctl2 = pon->baseaddr + PON_PS_HOLD_RST_CTL2;
	int ret;

	ret = regmap_update_bits(pon->regmap, ctl2, PON_PS_HOLD_RST_EN, 0);
	if (ret < 0)
		return ret;

	usleep_range(100, 200);

	ret = regmap_update_bits(pon->regmap, ctl, PON_PS_HOLD_TYPE_MASK,
				 PON_PS_HOLD_HARD_RESET);
	if (ret < 0)
		return ret;

	return regmap_update_bits(pon->regmap, ctl2, PON_PS_HOLD_RST_EN,
				  PON_PS_HOLD_RST_EN);
}

"""
DRVDATA = "\tplatform_set_drvdata(pdev, pon);\n"
ADD_CALL = """\tif (of_machine_is_compatible("microsoft,talkman")) {
		error = qcom_pon_set_hard_reset(pon);
		if (error < 0)
			dev_err(&pdev->dev, "can't set hard reset: %d\\n", error);
	}

"""


def main() -> None:
    path = Path(sys.argv[1]) / PON
    text = path.read_text()
    for anchor in (DEFINE, PROBE, DRVDATA):
        if text.count(anchor) != 1:
            sys.exit(f"patch-pon-reset: {PON}: anchor not found once: {anchor!r}")
    text = text.replace(DEFINE, DEFINE + ADD_DEFINE)
    text = text.replace(PROBE, ADD_FUNC + PROBE)
    text = text.replace(DRVDATA, ADD_CALL + DRVDATA)
    path.write_text(text)
    print("patch-pon-reset: a reboot resets the PMIC")


if __name__ == "__main__":
    main()
