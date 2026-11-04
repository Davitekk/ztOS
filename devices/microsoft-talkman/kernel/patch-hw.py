#!/usr/bin/env python3
"""Motion sensors, the motor, Wi-Fi and the audio DSP.

patch-hw.py <kernel source>

Adds two small drivers from drivers/ (the motion chip, the motor), teaches pcie-qcom this chip's
PCIe controller and 20 nm PHY, corrects its clocks and adds its reset, and appends hw-talkman.dtsi.

hw-talkman.dtsi also moves the audio DSP's memory to where this phone's secure firmware wants it,
and gives its loader the crypto engine's clock.

PCIe waits to be started, by `echo 1 > /sys/module/pcie_qcom/parameters/start` from
ztos-talkman-wifi.service, for two reasons: Wi-Fi's firmware is on the root file system, and a PCIe
fault then comes after SSH is up, not before.
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OCTAGON = "arch/arm64/boot/dts/qcom/msm8994-msft-lumia-octagon.dtsi"
TALKMAN = "arch/arm64/boot/dts/qcom/msm8992-msft-lumia-octagon-talkman.dts"
GCC = "drivers/clk/qcom/gcc-msm8994.c"
PCIE = "drivers/pci/controller/dwc/pcie-qcom.c"
GCC_IDS = "include/dt-bindings/clock/qcom,gcc-msm8994.h"
PAS = "drivers/remoteproc/qcom_q6v5_pas.c"

PAS_EDITS = [
    # The crypto engine's clock, taken only now and at the downstream kernel's 85.71 MHz: the
    # driver's second clock from here on, which it turns off when the DSP has taken over
    ("\tret = clk_prepare_enable(pas->aggre2_clk);\n",
     "\tif (!pas->aggre2_clk) {\n"
     "\t\tstruct of_phandle_args spec;\n\n"
     "\t\tif (!of_parse_phandle_with_args(pas->dev->of_node, \"ztos,crypto-clock\",\n"
     "\t\t\t\t\t\t\"#clock-cells\", 0, &spec)) {\n"
     "\t\t\tstruct clk *crypto = of_clk_get_from_provider(&spec);\n\n"
     "\t\t\tof_node_put(spec.np);\n"
     "\t\t\tif (!IS_ERR(crypto)) {\n"
     "\t\t\t\tclk_set_rate(crypto, 85710000);\n"
     "\t\t\t\tpas->aggre2_clk = crypto;\n"
     "\t\t\t}\n"
     "\t\t}\n"
     "\t}\n"
     "\tret = clk_prepare_enable(pas->aggre2_clk);\n"),
    ("#include <linux/clk.h>\n", "#include <linux/clk.h>\n#include <linux/clk-provider.h>\n#include <linux/of.h>\n"),
]

GCC_EDITS = [
    # The controller's own reset, which the tree's table leaves out
    ("\t[PCIE_PHY_0_RESET] = { 0x1b18 },\n", "\t[PCIE_PHY_0_RESET] = { 0x1b18 },\n\t[PCIE_0_CORE_RESET] = { 0x1ac0 },\n"),
    # The aux clock has no parent map either: setting its rate is a null pointer
    ("static struct clk_rcg2 pcie_0_aux_clk_src = {\n\t.cmd_rcgr = 0x1b00,\n",
     "static const struct parent_map gcc_pcie_aux_map[] = {\n\t{ P_XO, 0 },\n};\n\n"
     "static struct clk_rcg2 pcie_0_aux_clk_src = {\n\t.cmd_rcgr = 0x1b00,\n"
     "\t.parent_map = gcc_pcie_aux_map,\n"),
    # The pipe clock comes from the PHY, which is source 2 of this mux (downstream's
    # pcie_pipe_source_val). The tree's table has no parent map, so setting the rate fails.
    ("static struct clk_rcg2 pcie_0_pipe_clk_src = {\n\t.cmd_rcgr = 0x1adc,\n",
     "static const struct parent_map gcc_pcie_pipe_map[] = {\n\t{ P_XO, 2 },\n};\n\n"
     "static struct clk_rcg2 pcie_0_pipe_clk_src = {\n\t.cmd_rcgr = 0x1adc,\n"
     "\t.parent_map = gcc_pcie_pipe_map,\n"),
]

RES = """struct qcom_pcie_resources_8994 {
	struct clk_bulk_data clks[6];
	struct clk *pipe;
	struct clk *sleep;
	struct reset_control *core_reset;
	struct reset_control *phy_reset;
	void __iomem *phy;
	struct regulator_bulk_data supplies[5];
};

"""

# downstream drivers/pci/host/pci-msm.c, pcie_phy_init() for its 20 nm QMP PHY, 19.2 MHz
OPS = """/* Register and value, in order */
static const u16 pcie_8994_phy_seq[][2] = {
	{ 0x048, 0x08 }, { 0x0ac, 0x82 }, { 0x10c, 0x03 }, { 0x100, 0xd5 }, { 0x104, 0xaa },
	{ 0x108, 0x4d }, { 0x09c, 0x03 }, { 0x090, 0x06 }, { 0x094, 0x1a }, { 0x114, 0x7c },
	{ 0x034, 0x1f }, { 0x038, 0x12 }, { 0x03c, 0x0f }, { 0x024, 0x01 }, { 0x00c, 0x0f },
	{ 0x010, 0x0f }, { 0x014, 0x46 }, { 0x400, 0xf4 }, { 0x408, 0x2c }, { 0x004, 0xe1 },
	{ 0x04c, 0x91 }, { 0x050, 0x07 }, { 0x0e0, 0x20 }, { 0x0e8, 0x77 }, { 0x0f0, 0x15 },
	{ 0x268, 0x03 }, { 0x414, 0x09 }, { 0x418, 0x04 }, { 0x41c, 0x49 }, { 0x4a8, 0xff },
	{ 0x4ac, 0x1f }, { 0x4b0, 0xff }, { 0x4b4, 0x00 }, { 0x4bc, 0x1e }, { 0x4f0, 0x67 },
	{ 0x4f4, 0x80 }, { 0x4f8, 0x40 }, { 0x500, 0xb0 }, { 0x504, 0x06 }, { 0x110, 0x10 },
	{ 0x648, 0x10 }, { 0x650, 0xa3 }, { 0x654, 0x4b }, { 0x64c, 0x4d },
};

#define PCIE_8994_PHY_SW_RESET		0x600
#define PCIE_8994_PHY_POWER_DOWN	0x604
#define PCIE_8994_PHY_START		0x608
#define PCIE_8994_PHY_STATUS		0x728
#define PCIE_8994_PHY_NOT_READY		BIT(6)
#define PCIE_8994_PARF_WR_HALT		0x178
#define PCIE_8994_SEC_DEVICE		11

static int qcom_pcie_get_resources_8994(struct qcom_pcie *pcie)
{
	struct qcom_pcie_resources_8994 *res = &pcie->res.v8994;
	struct dw_pcie *pci = pcie->pci;
	struct device *dev = pci->dev;
	int ret;

	res->phy = devm_platform_ioremap_resource_byname(to_platform_device(dev), "phy");
	if (IS_ERR(res->phy))
		return PTR_ERR(res->phy);

	res->supplies[0].supply = "vdda";
	res->supplies[1].supply = "vddp";
	res->supplies[2].supply = "vdd-wlan-io";
	res->supplies[3].supply = "vdd-wlan-xtal";
	res->supplies[4].supply = "vddpe-3v3";
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(res->supplies), res->supplies);
	if (ret)
		return ret;

	res->clks[0].id = "aux";
	res->clks[1].id = "cfg";
	res->clks[2].id = "bus_master";
	res->clks[3].id = "bus_slave";
	res->clks[4].id = "ldo";
	res->clks[5].id = "ref";
	ret = devm_clk_bulk_get(dev, ARRAY_SIZE(res->clks), res->clks);
	if (ret)
		return ret;

	res->pipe = devm_clk_get(dev, "pipe");
	if (IS_ERR(res->pipe))
		return PTR_ERR(res->pipe);

	res->sleep = devm_clk_get(dev, "sleep");
	if (IS_ERR(res->sleep))
		return PTR_ERR(res->sleep);

	res->core_reset = devm_reset_control_get_exclusive(dev, "core");
	if (IS_ERR(res->core_reset))
		return PTR_ERR(res->core_reset);

	res->phy_reset = devm_reset_control_get_exclusive(dev, "phy");
	return PTR_ERR_OR_ZERO(res->phy_reset);
}

static void qcom_pcie_deinit_8994(struct qcom_pcie *pcie)
{
	struct qcom_pcie_resources_8994 *res = &pcie->res.v8994;

	writel(1, res->phy + PCIE_8994_PHY_SW_RESET);
	writel(0, res->phy + PCIE_8994_PHY_POWER_DOWN);
	writel(readl(pcie->parf + PARF_PHY_CTRL) | PHY_TEST_PWR_DOWN, pcie->parf + PARF_PHY_CTRL);
	clk_disable_unprepare(res->pipe);
	clk_bulk_disable_unprepare(ARRAY_SIZE(res->clks), res->clks);
	regulator_bulk_disable(ARRAY_SIZE(res->supplies), res->supplies);
}

static int qcom_pcie_init_8994(struct qcom_pcie *pcie)
{
	struct qcom_pcie_resources_8994 *res = &pcie->res.v8994;
	struct device *dev = pcie->pci->dev;
	int i, ret;

	/*
	 * The controller comes out of the boot chain unusable: without this reset the link trains
	 * to L0, yet no request leaves it, and every read of the card returns all ones.
	 */
	reset_control_assert(res->core_reset);
	usleep_range(10000, 11000);
	reset_control_deassert(res->core_reset);
	usleep_range(10000, 11000);

	ret = clk_prepare_enable(res->sleep);
	if (ret)
		return dev_err_probe(dev, ret, "sleep clock\\n");

	for (i = 0; i < ARRAY_SIZE(res->supplies); i++) {
		ret = regulator_enable(res->supplies[i].consumer);
		if (ret)
			return dev_err_probe(dev, ret, "supply %s\\n", res->supplies[i].supply);
	}

	ret = clk_set_rate(res->clks[0].clk, 1011000);
	if (ret)
		return dev_err_probe(dev, ret, "aux clock rate\\n");

	for (i = 0; i < ARRAY_SIZE(res->clks); i++) {
		ret = clk_prepare_enable(res->clks[i].clk);
		if (ret)
			return dev_err_probe(dev, ret, "clock %s\\n", res->clks[i].id);
	}

	reset_control_assert(res->phy_reset);
	usleep_range(100, 200);
	reset_control_deassert(res->phy_reset);
	usleep_range(100, 200);

	ret = qcom_scm_restore_sec_cfg(PCIE_8994_SEC_DEVICE, 0);
	if (ret)
		dev_warn(dev, "restore_sec_cfg: %d\\n", ret);
	return 0;
}

static int qcom_pcie_post_init_8994(struct qcom_pcie *pcie)
{
	struct qcom_pcie_resources_8994 *res = &pcie->res.v8994;
	struct device *dev = pcie->pci->dev;
	u32 status;
	int i, ret;

	writel(readl(pcie->parf + PARF_PHY_CTRL) & ~PHY_TEST_PWR_DOWN, pcie->parf + PARF_PHY_CTRL);
	writel(0, pcie->parf + PARF_DBI_BASE_ADDR);
	writel(0x365e, pcie->parf + PARF_SYS_CTRL);
	writel(SZ_16M, pcie->parf + PARF_SLV_ADDR_SPACE_SIZE);
	writel(readl(pcie->parf + PCIE_8994_PARF_WR_HALT) | BIT(31),
	       pcie->parf + PCIE_8994_PARF_WR_HALT);
	wmb();

	writel(3, res->phy + PCIE_8994_PHY_POWER_DOWN);
	for (i = 0; i < ARRAY_SIZE(pcie_8994_phy_seq); i++)
		writel(pcie_8994_phy_seq[i][1], res->phy + pcie_8994_phy_seq[i][0]);
	writel(0, res->phy + PCIE_8994_PHY_SW_RESET);
	writel(3, res->phy + PCIE_8994_PHY_START);
	wmb();
	usleep_range(1000, 1100);

	ret = clk_set_rate(res->pipe, 125000000);
	if (ret)
		dev_warn(dev, "pipe clock rate: %d\\n", ret);
	ret = clk_prepare_enable(res->pipe);
	if (ret)
		return dev_err_probe(dev, ret, "pipe clock\\n");

	ret = readl_poll_timeout(res->phy + PCIE_8994_PHY_STATUS, status,
				 !(status & PCIE_8994_PHY_NOT_READY), 1000, 100000);
	if (ret) {
		dev_err(dev, "PHY not ready: status %x\\n", status);
		return ret;
	}
	qcom_pcie_set_slot_cap(pcie->pci);
	return 0;
}

static const struct qcom_pcie_ops ops_8994 = {
	.get_resources = qcom_pcie_get_resources_8994,
	.init = qcom_pcie_init_8994,
	.post_init = qcom_pcie_post_init_8994,
	.deinit = qcom_pcie_deinit_8994,
	.ltssm_enable = qcom_pcie_2_3_2_ltssm_enable,
};

"""

START = """static int qcom_pcie_start_set(const char *val, const struct kernel_param *kp)
{
	static bool registered;

	if (registered)
		return 0;
	registered = true;
	return platform_driver_register(&qcom_pcie_driver);
}

static const struct kernel_param_ops qcom_pcie_start_ops = {
	.set = qcom_pcie_start_set,
};
module_param_cb(start, &qcom_pcie_start_ops, NULL, 0200);
"""

PCIE_EDITS = [
    ("union qcom_pcie_resources {\n", RES + "union qcom_pcie_resources {\n\tstruct qcom_pcie_resources_8994 v8994;\n"),
    ("static const struct qcom_pcie_ops ops_2_3_2 = {\n", OPS + "static const struct qcom_pcie_ops ops_2_3_2 = {\n"),
    ("static const struct qcom_pcie_cfg cfg_2_3_2 = {\n",
     "static const struct qcom_pcie_cfg cfg_8994 = {\n\t.ops = &ops_8994,\n\t.no_l0s = true,\n};\n\n"
     "static const struct qcom_pcie_cfg cfg_2_3_2 = {\n"),
    ('\t{ .compatible = "qcom,pcie-msm8996", .data = &cfg_2_3_2 },\n',
     '\t{ .compatible = "qcom,pcie-msm8994", .data = &cfg_8994 },\n'
     '\t{ .compatible = "qcom,pcie-msm8996", .data = &cfg_2_3_2 },\n'),
    ("builtin_platform_driver(qcom_pcie_driver);\n", START),
    ("#include <linux/reset.h>\n",
     "#include <linux/reset.h>\n#include <linux/firmware/qcom/qcom_scm.h>\n#include <linux/moduleparam.h>\n"),
]


def edit(path, edits):
    text = path.read_text()
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit(f"patch-hw: {path.name}: not found once: {old!r}")
        text = text.replace(old, new)
    path.write_text(text)


def add_kconfig(path, before, block):
    text = path.read_text()
    if text.count(before) != 1:
        sys.exit(f"patch-hw: {path}: not found once: {before!r}")
    path.write_text(text.replace(before, block + "\n" + before))


def main():
    source = Path(sys.argv[1])

    edit(source / OCTAGON, [('compatible = "invensense,mpu6500";', 'compatible = "invensense,icm20x48";')])
    edit(source / GCC, GCC_EDITS)
    edit(source / GCC_IDS, [("#define MSS_RESET\t\t\t\t5\n", "#define MSS_RESET\t\t\t\t5\n#define PCIE_0_CORE_RESET\t\t6\n")])
    edit(source / PCIE, PCIE_EDITS)
    edit(source / PAS, PAS_EDITS)

    imu = source / "drivers/iio/imu"
    shutil.copy(HERE / "drivers/icm20x48.c", imu)
    add_kconfig(imu / "Kconfig", 'source "drivers/iio/imu/bmi160/Kconfig"\n',
                'config ICM20X48\n\ttristate "ICM-20x48 family accelerometer and gyroscope"\n'
                '\tdepends on I2C\n')
    with (imu / "Makefile").open("a") as make:
        make.write("obj-$(CONFIG_ICM20X48) += icm20x48.o\n")

    misc = source / "drivers/input/misc"
    shutil.copy(HERE / "drivers/pmi8994-haptics.c", misc)
    add_kconfig(misc / "Kconfig", "config INPUT_PM8XXX_VIBRATOR\n",
                'config INPUT_PMI8994_HAPTICS\n\ttristate "PMI8994 haptics"\n'
                '\tdepends on MFD_SPMI_PMIC\n\tselect INPUT_FF_MEMLESS\n')
    with (misc / "Makefile").open("a") as make:
        make.write("obj-$(CONFIG_INPUT_PMI8994_HAPTICS) += pmi8994-haptics.o\n")

    path = source / TALKMAN
    path.write_text(path.read_text() + "\n" + (HERE / "hw-talkman.dtsi").read_text())
    print("patch-hw: the motion chip, the motor, PCIe and Wi-Fi's power")


if __name__ == "__main__":
    main()
