#!/usr/bin/env python3
"""The Lumia 950's USB port: what LK's fastboot mode does and this driver doesn't.

USB only worked on a kernel started by fastboot. Booted directly from the boot
partition, the gadget binds and stays "not attached", and the computer sees an
unknown device, because the tree's dwc3-qcom-legacy, which serves this phone's
qcom,dwc3 node, leaves two things to the bootloader:

- A TCSR register at 0xfd4ab000 routes the USB PHY to the controller. Android's
  dwc3-msm writes 1 to it on every probe ("Enable USB3 on the primary USB port"), LK
  when it enters fastboot ("set the mux for snps controller").
- The wrapper's PHY settings, which LK programs in usb30_wrapper.c: PARAMETER_OVERRIDE_X,
  HS_PHY_CTRL_COMMON, HS_PHY_CTRL and SS_PHY_CTRL, including what enables the D+ pull-up
  a host sees a device by. The values are the ones read from this phone with USB working
  after fastboot.

Usage: patch-dwc3-usb-sel.py <kernel source>
"""
import sys
from pathlib import Path

DWC3 = "drivers/usb/dwc3/dwc3-qcom-legacy.c"
MUX_ANCHOR = "\tret = reset_control_assert(qcom->resets);\n"
MUX = """	if (of_machine_is_compatible("microsoft,talkman")) {
		void __iomem *usb_sel = ioremap(0xfd4ab000, 4);

		if (!usb_sel)
			return -ENOMEM;
		writel(1, usb_sel);
		/* done before the controller's registers are touched */
		mb();
		iounmap(usb_sel);
	}

"""
PHY_ANCHOR = "\tret = dwc3_qcom_setup_irq(pdev);\n"
PHY = """	if (of_machine_is_compatible("microsoft,talkman")) {
		dev_info(dev, "wrapper at probe: hs %08x override %08x common %08x ss %08x\\n",
			 readl(qcom->qscratch_base + 0x10),
			 readl(qcom->qscratch_base + 0x14),
			 readl(qcom->qscratch_base + 0xec),
			 readl(qcom->qscratch_base + 0x30));
		writel(0x00d190e4, qcom->qscratch_base + 0x14);
		writel(0x0071dc88, qcom->qscratch_base + 0xec);
		writel(0x1c302800, qcom->qscratch_base + 0x10);
		writel(0x71210102, qcom->qscratch_base + 0x30);
		/* done before the controller's registers are touched */
		mb();
	}

"""


def main() -> None:
    path = Path(sys.argv[1]) / DWC3
    text = path.read_text()
    for anchor in (MUX_ANCHOR, PHY_ANCHOR):
        if text.count(anchor) != 1:
            sys.exit(f"patch-dwc3-usb-sel: {DWC3}: anchor not found once: {anchor!r}")
    text = text.replace(MUX_ANCHOR, MUX + MUX_ANCHOR)
    text = text.replace(PHY_ANCHOR, PHY + PHY_ANCHOR)
    path.write_text(text)
    print("patch-dwc3-usb-sel: the USB port and its PHY settings, as LK leaves them")


if __name__ == "__main__":
    main()
