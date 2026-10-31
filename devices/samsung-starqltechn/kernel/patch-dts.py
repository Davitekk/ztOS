#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""The Galaxy S9 (Snapdragon) device tree, as ztOS uses it: upstream's
sdm845-samsung-starqltechn.dts with what it does not have yet.

Added: Wi-Fi and Bluetooth, one BCM4361 B2 (Murata 1QW module): Wi-Fi on
PCIe0 (brcmfmac), Bluetooth on the QUP UART of SE6 (hci_bcm serdev). Every
pin is the stock kernel's, read from the SCV38's own boot image (board
"STARQLTE JPN" Rev14, the tree its bootloader picks for hw_rev 15):

  bcmdhd_wlan    wlan-en-gpio = <&tlmm 99>, wlan-host-wake-gpio = <&tlmm 116>
  pcie0          perst-gpio = <&tlmm 35>, wake-gpio = <&tlmm 37>, clkreq gpio36
                 vreg-0.9 = 880 mV (L1A), vreg-1.8 = 1200 mV (L26A): the QMP PHY's
  bt_driver      bcm,bt-reset-gpio = <&pm8998_gpios 3>
  bt_bluesleep   bcm,bt-wake-gpio = <&tlmm 136>, bcm,bt-host-wake-gpio = <&tlmm 108>
  hsuart0        qcom,qup_uart@0x898000 (SE6, 4 wire: gpio45-48), 3 Mbaud

Every edit asserts its anchor, so an upstream change that moves something
fails the build here instead of booting a phone with a wrong tree.
Takes the kernel source directory as its only argument; idempotent.
"""
import sys
from pathlib import Path

src = Path(sys.argv[1])
DTS = src / "arch/arm64/boot/dts/qcom/sdm845-samsung-starqltechn.dts"
DTSI = src / "arch/arm64/boot/dts/qcom/sdm845.dtsi"
dts = DTS.read_text()
dtsi = DTSI.read_text()
orig = dts
MARK = "/* ztOS: BCM4361 Wi-Fi and Bluetooth */"

# The tree we were written against: SM-G9600's, which the SCV38 shares.
assert 'model = "Samsung Galaxy S9 SM-G9600";' in dts, f"{DTS}: not the starqltechn tree we know"
assert 'compatible = "samsung,starqltechn", "qcom,sdm845";' in dts
# what the additions refer to
for label in ("pcie0: pcie@1c00000", "pcie0_phy: phy@1c06000", "uart6: serial@898000",
              "qup_uart6_4pin: qup-uart6-4pin-state"):
    assert label in dtsi, f"{DTSI.name}: {label} not found"
for label in ("vreg_l1a_0p875: ldo1", "vreg_l26a_1p2: ldo26", "&pm8998_gpios {", "&tlmm {"):
    assert label in dts, f"{DTS.name}: {label} not found"
# nothing upstream claims these yet
for taken in ("&pcie0 {", "&pcie0_phy {", "&uart6 {", "<&tlmm 99 ", "<&tlmm 116 ", "<&tlmm 136 ",
              "<&tlmm 108 ", '"gpio99"', '"gpio136"', '"gpio108"', '"gpio35"', '"gpio37"'):
    assert MARK in dts or taken not in dts, f"{DTS.name}: {taken} already used upstream: look again"

ROOT_NODE = """
	/*
	 * The debug UART (SE9) is a GENI console port, which only probes as
	 * line 0 of a "serial" alias; without one it fails ("Invalid line -19")
	 * and holds the interconnects, clocks and power domains at their boot
	 * levels (sync_state pending) for good. serial1: Bluetooth, a fixed name.
	 */
	aliases {
		serial0 = &uart9;
		serial1 = &uart6;
	};

	/*
	 * WL_REG_ON: the BCM4361's Wi-Fi half. As PCIe0's slot supply the
	 * controller driver raises it before the link comes up and waits the
	 * chip's start-up time; Android's bcmdhd held it 100 ms before PERST#.
	 */
	wlan_en: regulator-wlan-en {
		compatible = "regulator-fixed";
		regulator-name = "wlan_en";
		regulator-min-microvolt = <3300000>;
		regulator-max-microvolt = <3300000>;

		gpio = <&tlmm 99 GPIO_ACTIVE_HIGH>;
		enable-active-high;
		startup-delay-us = <100000>;

		pinctrl-0 = <&wlan_en_default>;
		pinctrl-names = "default";
	};
"""

NODES = """
""" + MARK + """
&pcie0 {
	perst-gpios = <&tlmm 35 GPIO_ACTIVE_LOW>;
	wake-gpios = <&tlmm 37 GPIO_ACTIVE_HIGH>;
	vddpe-3v3-supply = <&wlan_en>;

	pinctrl-0 = <&pcie0_default_state>;
	pinctrl-names = "default";

	status = "okay";
};

&pcie0_phy {
	vdda-phy-supply = <&vreg_l1a_0p875>;
	vdda-pll-supply = <&vreg_l26a_1p2>;

	status = "okay";
};

&uart6 {
	pinctrl-0 = <&qup_uart6_4pin>;

	status = "okay";

	bluetooth {
		compatible = "brcm,bcm4329-bt";

		shutdown-gpios = <&pm8998_gpios 3 GPIO_ACTIVE_HIGH>;
		device-wakeup-gpios = <&tlmm 136 GPIO_ACTIVE_HIGH>;
		host-wakeup-gpios = <&tlmm 108 GPIO_ACTIVE_HIGH>;
		max-speed = <3000000>;

		pinctrl-0 = <&bt_en_default>, <&bt_wake_default>, <&bt_host_wake_default>;
		pinctrl-names = "default";
	};
};
"""

TLMM_STATES = """
	pcie0_default_state: pcie0-default-state {
		clkreq-pins {
			pins = "gpio36";
			function = "pci_e0";
			bias-pull-up;
		};

		reset-n-pins {
			pins = "gpio35";
			function = "gpio";
			drive-strength = <2>;
			output-low;
			bias-pull-down;
		};

		wake-n-pins {
			pins = "gpio37";
			function = "gpio";
			drive-strength = <2>;
			bias-pull-up;
		};
	};

	wlan_en_default: wlan-en-default-state {
		pins = "gpio99";
		function = "gpio";
		drive-strength = <2>;
		bias-pull-down;
	};

	bt_wake_default: bt-wake-default-state {
		pins = "gpio136";
		function = "gpio";
		drive-strength = <2>;
		bias-pull-down;
	};

	bt_host_wake_default: bt-host-wake-default-state {
		pins = "gpio108";
		function = "gpio";
		drive-strength = <2>;
		bias-pull-down;
	};
"""

PMIC_STATES = """
	bt_en_default: bt-en-default-state {
		pins = "gpio3";
		function = "normal";
		power-source = <0>;
		input-disable;
		output-low;
	};
"""

# The MAX77705's USB-C MCU, at its fixed address beside the PMIC (0x66),
# charger (0x69) and gauge (0x36): Samsung's driver makes it a client of its
# own, so the stock tree names only 0x66. kernel/drivers/s9p-max77705-muic.c.
I2C14_USBC = """
	/* D+/D- to the AP: TWRP's shutdown resets the MCU, leaving them open */
	usbc@25 {
		compatible = "samsung,s9p-max77705-muic";
		reg = <0x25>;
	};
"""

if MARK not in dts:
    # the regulator goes into the root node, after its first child (battery)
    anchor = "\tbattery: battery {\n"
    assert dts.count(anchor) == 1, f"{DTS.name}: battery anchor"
    start = dts.index(anchor)
    end = dts.index("\n\t};\n", start) + len("\n\t};\n")
    dts = dts[:end] + ROOT_NODE + dts[end:]

    for node, states in (("&tlmm {\n", TLMM_STATES), ("&pm8998_gpios {\n", PMIC_STATES),
                         ("&i2c14 {\n", I2C14_USBC)):
        assert dts.count(node) == 1, f"{DTS.name}: {node.strip()} anchor"
        start = dts.index(node)
        # the node's closing brace: the first "\n};\n" after it
        end = dts.index("\n};\n", start)
        dts = dts[:end] + "\n" + states.rstrip("\n") + dts[end:]

    dts = dts.rstrip("\n") + "\n" + NODES

    # Bixby: upstream makes it Enter (postmarketOS's way to confirm before the
    # system is up); on ztOS a stray press would type into the app in front.
    # KEY_ASSISTANT is the key's own meaning, and nothing takes it by default.
    old = '\t\t\tlabel = "Bixby";\n\t\t\tgpios = <&pm8998_gpios 19 GPIO_ACTIVE_LOW>;\n\t\t\tlinux,code = <KEY_ENTER>;\n'
    assert dts.count(old) == 1, f"{DTS.name}: Bixby key anchor"
    dts = dts.replace(old, old.replace("KEY_ENTER", "KEY_ASSISTANT"))

if dts != orig:
    DTS.write_text(dts)
    print(f"{DTS.name}: Wi-Fi (PCIe0) and Bluetooth (UART6) added")
else:
    print(f"{DTS.name}: already patched")
