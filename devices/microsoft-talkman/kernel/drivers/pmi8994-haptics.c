// SPDX-License-Identifier: GPL-2.0-only
/*
 * The vibration motor on PMI8994's haptics block, in direct mode, for an ERM motor (one with an
 * off-centre weight). The settings are those of the phone's own downstream device tree: 2.3 V at
 * most, 800 mA limit, 505 kHz, square wave. Strength scales the voltage.
 */
#include <linux/input.h>
#include <linux/jiffies.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/regmap.h>
#include <linux/workqueue.h>

#define HAP_STATUS	0x0a
#define HAP_EN_CTL	0x46
#define HAP_EN_CTL2	0x48
#define HAP_ACT_TYPE	0x4c
#define HAP_WAV_SHAPE	0x4d
#define HAP_PLAY_MODE	0x4e
#define HAP_AUTO_RES	0x4f
#define HAP_VMAX	0x51
#define HAP_ILIM	0x52
#define HAP_SC_DEB	0x53
#define HAP_RATE_CFG1	0x54
#define HAP_RATE_CFG2	0x55
#define HAP_INT_PWM	0x56
#define HAP_PWM_CAP	0x58
#define HAP_SC_CLR	0x59
#define HAP_BRAKE	0x5c
#define HAP_PLAY	0x70

#define STATUS_SC	BIT(3)
#define EN_CTL_EN	BIT(7)
#define PLAY_EN		BIT(7)
#define VMAX_STEP_MV	116
#define VMAX_MV		2300
#define VMAX_MASK	GENMASK(5, 1)
#define LONGEST_MS	15000		/* whatever userspace asks for, or forgets to stop */

struct hap {
	struct regmap *map;
	u32 base;
	struct input_dev *input;
	struct work_struct set;
	struct delayed_work stop;
	u16 strength;
	bool on;
};

static int hap_w(struct hap *hap, u32 reg, u8 val)
{
	return regmap_write(hap->map, hap->base + reg, val);
}

static int hap_u(struct hap *hap, u32 reg, u8 mask, u8 val)
{
	return regmap_update_bits(hap->map, hap->base + reg, mask, val);
}

static void hap_off(struct hap *hap)
{
	hap_w(hap, HAP_PLAY, 0);
	hap_w(hap, HAP_EN_CTL, 0);
	hap->on = false;
}

static void hap_set_work(struct work_struct *work)
{
	struct hap *hap = container_of(work, struct hap, set);
	u16 strength = READ_ONCE(hap->strength);
	unsigned int status, steps;

	if (!strength) {
		cancel_delayed_work(&hap->stop);
		hap_off(hap);
		return;
	}
	if (!regmap_read(hap->map, hap->base + HAP_STATUS, &status) && (status & STATUS_SC))
		hap_w(hap, HAP_SC_CLR, 1);

	steps = DIV_ROUND_UP(VMAX_MV / VMAX_STEP_MV * (u32)strength, 0xffff);
	hap_u(hap, HAP_VMAX, VMAX_MASK, steps << 1);
	if (!hap->on) {
		hap_w(hap, HAP_EN_CTL, EN_CTL_EN);
		hap_w(hap, HAP_PLAY, PLAY_EN);
		hap->on = true;
	}
	mod_delayed_work(system_wq, &hap->stop, msecs_to_jiffies(LONGEST_MS));
}

static void hap_stop_work(struct work_struct *work)
{
	hap_off(container_of(to_delayed_work(work), struct hap, stop));
}

static int hap_play(struct input_dev *input, void *data, struct ff_effect *effect)
{
	struct hap *hap = input_get_drvdata(input);
	u16 strength = effect->u.rumble.strong_magnitude;

	if (!strength)
		strength = effect->u.rumble.weak_magnitude;
	WRITE_ONCE(hap->strength, strength);
	schedule_work(&hap->set);
	return 0;
}

static void hap_close(struct input_dev *input)
{
	struct hap *hap = input_get_drvdata(input);

	cancel_work_sync(&hap->set);
	cancel_delayed_work_sync(&hap->stop);
	hap_off(hap);
}

static int hap_config(struct hap *hap)
{
	int ret = 0;

	ret |= hap_u(hap, HAP_ACT_TYPE, BIT(0), 1);		/* ERM */
	ret |= hap_w(hap, HAP_AUTO_RES, 0);			/* resonance is for LRA motors */
	ret |= hap_u(hap, HAP_PLAY_MODE, GENMASK(5, 4), 0);	/* direct */
	ret |= hap_u(hap, HAP_VMAX, VMAX_MASK, (VMAX_MV / VMAX_STEP_MV) << 1);
	ret |= hap_u(hap, HAP_ILIM, BIT(0), 1);			/* 800 mA */
	ret |= hap_u(hap, HAP_SC_DEB, GENMASK(2, 0), 1);	/* 8 cycles */
	ret |= hap_u(hap, HAP_INT_PWM, GENMASK(1, 0), 1);	/* 505 kHz */
	ret |= hap_u(hap, HAP_PWM_CAP, GENMASK(1, 0), 1);
	ret |= hap_u(hap, HAP_WAV_SHAPE, BIT(0), 1);		/* square */
	ret |= hap_w(hap, HAP_RATE_CFG1, 5263 / 5 & 0xff);	/* the downstream default, 5263 us */
	ret |= hap_u(hap, HAP_RATE_CFG2, GENMASK(3, 0), 5263 / 5 >> 8);
	ret |= hap_u(hap, HAP_EN_CTL2, BIT(0), 1);		/* brake */
	ret |= hap_w(hap, HAP_BRAKE, 0x54);			/* pattern 0, 1, 1, 1 */
	return ret ? -EIO : 0;
}

static int hap_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct hap *hap;
	int ret;

	hap = devm_kzalloc(dev, sizeof(*hap), GFP_KERNEL);
	if (!hap)
		return -ENOMEM;
	hap->map = dev_get_regmap(dev->parent, NULL);
	if (!hap->map)
		return -ENODEV;
	ret = device_property_read_u32(dev, "reg", &hap->base);
	if (ret)
		return ret;
	INIT_WORK(&hap->set, hap_set_work);
	INIT_DELAYED_WORK(&hap->stop, hap_stop_work);

	ret = hap_config(hap);
	if (ret)
		return dev_err_probe(dev, ret, "configuring\n");

	hap->input = devm_input_allocate_device(dev);
	if (!hap->input)
		return -ENOMEM;
	hap->input->name = "pmi8994-haptics";
	hap->input->id.bustype = BUS_HOST;
	hap->input->close = hap_close;
	input_set_drvdata(hap->input, hap);
	input_set_capability(hap->input, EV_FF, FF_RUMBLE);
	ret = input_ff_create_memless(hap->input, NULL, hap_play);
	if (ret)
		return ret;
	return input_register_device(hap->input);
}

static const struct of_device_id hap_of_match[] = {
	{ .compatible = "qcom,pmi8994-haptics" },
	{ }
};
MODULE_DEVICE_TABLE(of, hap_of_match);

static struct platform_driver hap_driver = {
	.probe = hap_probe,
	.driver = {
		.name = "pmi8994-haptics",
		.of_match_table = hap_of_match,
	},
};
module_platform_driver(hap_driver);

MODULE_DESCRIPTION("PMI8994 haptics");
MODULE_LICENSE("GPL");
