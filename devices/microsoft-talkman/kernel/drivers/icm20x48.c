// SPDX-License-Identifier: GPL-2.0-only
/*
 * The Lumia 950's motion chip: accelerometer and gyroscope at I2C address 0x68.
 *
 * The device trees call it an MPU-6500, and the inv_mpu6050 driver gives up on it, as register
 * 0x75 reads 0. Its registers are those of InvenSense's ICM-20x48 family instead: who-am-I at
 * 0x00 (0xAB here), PWR_MGMT_1 at 0x06, the samples from 0x2D, four register banks. All were
 * tried on the phone. Reset defaults are used: +-2 g, +-250 degrees/s.
 *
 * It sleeps unless read: awake on the first read, asleep again 2 s after the last one.
 */
#include <linux/delay.h>
#include <linux/i2c.h>
#include <linux/iio/iio.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/regulator/consumer.h>
#include <linux/workqueue.h>

#define REG_WHO_AM_I	0x00
#define REG_PWR_MGMT_1	0x06
#define REG_PWR_MGMT_2	0x07
#define REG_ACCEL	0x2d
#define REG_GYRO	0x33
#define REG_TEMP	0x39
#define REG_BANK_SEL	0x7f

#define PWR1_SLEEP	0x40
#define PWR1_CLK_AUTO	0x01
#define WHO_THIS_CHIP	0xab

#define WAKE_MS		35		/* the gyroscope's start-up time */
#define STAY_AWAKE_MS	2000

struct icm {
	struct i2c_client *client;
	struct mutex lock;
	struct delayed_work sleep;
	struct iio_mount_matrix orientation;
	bool awake;
};

static const struct iio_mount_matrix *icm_orientation(const struct iio_dev *indio,
						      const struct iio_chan_spec *chan)
{
	struct icm *icm = iio_priv(indio);

	return &icm->orientation;
}

static const struct iio_chan_spec_ext_info icm_ext_info[] = {
	IIO_MOUNT_MATRIX(IIO_SHARED_BY_TYPE, icm_orientation),
	{ }
};

#define ICM_AXIS(_type, _mod, _reg) {					\
	.type = _type,							\
	.modified = 1,							\
	.channel2 = _mod,						\
	.address = _reg,						\
	.info_mask_separate = BIT(IIO_CHAN_INFO_RAW),			\
	.info_mask_shared_by_type = BIT(IIO_CHAN_INFO_SCALE),		\
	.ext_info = icm_ext_info,					\
}

static const struct iio_chan_spec icm_channels[] = {
	ICM_AXIS(IIO_ACCEL, IIO_MOD_X, REG_ACCEL),
	ICM_AXIS(IIO_ACCEL, IIO_MOD_Y, REG_ACCEL + 2),
	ICM_AXIS(IIO_ACCEL, IIO_MOD_Z, REG_ACCEL + 4),
	ICM_AXIS(IIO_ANGL_VEL, IIO_MOD_X, REG_GYRO),
	ICM_AXIS(IIO_ANGL_VEL, IIO_MOD_Y, REG_GYRO + 2),
	ICM_AXIS(IIO_ANGL_VEL, IIO_MOD_Z, REG_GYRO + 4),
	{
		.type = IIO_TEMP,
		.address = REG_TEMP,
		.info_mask_separate = BIT(IIO_CHAN_INFO_RAW) | BIT(IIO_CHAN_INFO_SCALE) |
				      BIT(IIO_CHAN_INFO_OFFSET),
	},
};

static int icm_wake(struct icm *icm)
{
	int ret;

	if (icm->awake)
		return 0;
	ret = i2c_smbus_write_byte_data(icm->client, REG_PWR_MGMT_1, PWR1_CLK_AUTO);
	if (ret)
		return ret;
	usleep_range(1000, 2000);
	ret = i2c_smbus_write_byte_data(icm->client, REG_PWR_MGMT_2, 0);
	if (ret)
		return ret;
	msleep(WAKE_MS);
	icm->awake = true;
	return 0;
}

static void icm_sleep_work(struct work_struct *work)
{
	struct icm *icm = container_of(to_delayed_work(work), struct icm, sleep);

	mutex_lock(&icm->lock);
	if (!i2c_smbus_write_byte_data(icm->client, REG_PWR_MGMT_1, PWR1_SLEEP | PWR1_CLK_AUTO))
		icm->awake = false;
	mutex_unlock(&icm->lock);
}

static int icm_read_raw(struct iio_dev *indio, struct iio_chan_spec const *chan,
			int *val, int *val2, long mask)
{
	struct icm *icm = iio_priv(indio);
	int ret;

	switch (mask) {
	case IIO_CHAN_INFO_RAW:
		mutex_lock(&icm->lock);
		ret = icm_wake(icm);
		if (!ret)
			ret = i2c_smbus_read_word_swapped(icm->client, chan->address);
		mutex_unlock(&icm->lock);
		mod_delayed_work(system_wq, &icm->sleep, msecs_to_jiffies(STAY_AWAKE_MS));
		if (ret < 0)
			return ret;
		*val = (s16)ret;
		return IIO_VAL_INT;
	case IIO_CHAN_INFO_SCALE:
		*val = 0;
		if (chan->type == IIO_ACCEL) {
			*val2 = 598550;		/* 9.80665 m/s2 / 16384 */
			return IIO_VAL_INT_PLUS_NANO;
		}
		if (chan->type == IIO_ANGL_VEL) {
			*val2 = 133231;		/* pi / 180 rad/s / 131 */
			return IIO_VAL_INT_PLUS_NANO;
		}
		*val = 2;			/* millidegrees: 1000 / 333.87 */
		*val2 = 995178;
		return IIO_VAL_INT_PLUS_MICRO;
	case IIO_CHAN_INFO_OFFSET:
		*val = 7011;			/* 21 C at raw 0 */
		return IIO_VAL_INT;
	}
	return -EINVAL;
}

static const struct iio_info icm_info = {
	.read_raw = icm_read_raw,
};

static void icm_cancel_sleep(void *data)
{
	struct icm *icm = data;

	cancel_delayed_work_sync(&icm->sleep);
	i2c_smbus_write_byte_data(icm->client, REG_PWR_MGMT_1, PWR1_SLEEP | PWR1_CLK_AUTO);
}

static int icm_probe(struct i2c_client *client)
{
	static const char * const supplies[] = { "vdd", "vddio" };
	struct device *dev = &client->dev;
	struct iio_dev *indio;
	struct icm *icm;
	int ret;

	indio = devm_iio_device_alloc(dev, sizeof(*icm));
	if (!indio)
		return -ENOMEM;
	icm = iio_priv(indio);
	icm->client = client;
	mutex_init(&icm->lock);
	INIT_DELAYED_WORK(&icm->sleep, icm_sleep_work);

	ret = iio_read_mount_matrix(dev, &icm->orientation);
	if (ret)
		return ret;

	ret = devm_regulator_bulk_get_enable(dev, ARRAY_SIZE(supplies), supplies);
	if (ret)
		return dev_err_probe(dev, ret, "supplies\n");
	msleep(20);

	ret = i2c_smbus_write_byte_data(client, REG_BANK_SEL, 0);
	if (ret)
		return dev_err_probe(dev, ret, "no answer\n");
	ret = i2c_smbus_read_byte_data(client, REG_WHO_AM_I);
	if (ret < 0)
		return ret;
	if (ret != WHO_THIS_CHIP)
		return dev_err_probe(dev, -ENODEV, "who-am-I 0x%02x\n", ret);

	ret = devm_add_action_or_reset(dev, icm_cancel_sleep, icm);
	if (ret)
		return ret;

	indio->name = "icm20x48";
	indio->info = &icm_info;
	indio->modes = INDIO_DIRECT_MODE;
	indio->channels = icm_channels;
	indio->num_channels = ARRAY_SIZE(icm_channels);
	return devm_iio_device_register(dev, indio);
}

static const struct of_device_id icm_of_match[] = {
	{ .compatible = "invensense,icm20x48" },
	{ }
};
MODULE_DEVICE_TABLE(of, icm_of_match);

static struct i2c_driver icm_driver = {
	.driver = {
		.name = "icm20x48",
		.of_match_table = icm_of_match,
	},
	.probe = icm_probe,
};
module_i2c_driver(icm_driver);

MODULE_DESCRIPTION("ICM-20x48 family accelerometer and gyroscope");
MODULE_LICENSE("GPL");
