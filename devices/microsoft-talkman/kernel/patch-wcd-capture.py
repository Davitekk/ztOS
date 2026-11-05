#!/usr/bin/env python3
"""The Lumia 950's microphones: capture on the WCD9330. Not working yet: it records silence.

Nothing reaches this code in a normal boot. See wip-codec-card.dtsi for how to try it and what is known.


The tree's driver only plays. This adds one capture stream of two channels from the phone's digital
microphones, on the codec's fixed paths: DMICn into decimator n into SLIMbus TX port n-1. Which pair of
lines is the "Mic Select" control's. Sequences and registers are from the phone's Android kernel, 3.10
wcd9330.c (dmic, dec, micbias, ldo_h, set_tx_sb_port_format) and wcd9xxx-slimslave.c (cfg_slim_sch_tx),
without its DAPM: the path does not change while it runs, so the stream turns it on and off in one go.

Usage: patch-wcd-capture.py <kernel source>
"""
import sys
from pathlib import Path

CODEC = "sound/soc/codecs/wcd9330.c"

FUNCTIONS = r"""/* Capture: see devices/microsoft-talkman/kernel/patch-wcd-capture.py */
#define WCD_LDO_H_MODE_1	0x110
#define WCD_MICB_CFILT_1_CTL	0x128
#define WCD_MICB_CFILT_1_VAL	0x129
#define WCD_MICB_1_CTL		0x12b
#define WCD_MICB_1_INT_RBIAS	0x12c
#define WCD_MICB_CFILT_3_CTL	0x134
#define WCD_MICB_CFILT_3_VAL	0x135
#define WCD_MICB_3_CTL		0x137
#define WCD_MICB_3_INT_RBIAS	0x138
#define WCD_MICB_4_CTL		0x13a
#define WCD_MICB_4_INT_RBIAS	0x13b
#define WCD_DMIC_B1_CTL		0x04a
#define WCD_DMIC_B2_CTL		0x04b
#define WCD_TX_VOL_GAIN(d)	(0x221 + 8 * ((d) - 1))
#define WCD_TX_VOL_CFG(d)	(0x222 + 8 * ((d) - 1))
#define WCD_TX_MUX_CTL(d)	(0x223 + 8 * ((d) - 1))
#define WCD_TX_CLK_FS(d)	(0x224 + 8 * ((d) - 1))
#define WCD_TX_DMIC_CTL(d)	(0x225 + 8 * ((d) - 1))
#define WCD_CLK_TX_RESET_B1	0x302
#define WCD_CLK_TX_EN_B1	0x30a
#define WCD_CONN_TX_B1		0x393
#define WCD_CONN_TX_SB(p)	(0x3a3 + (p))
#define WCD_PGD_TX_MULTI_0(p)	(0x100 + 4 * (p))
#define WCD_PGD_TX_MULTI_1(p)	(0x101 + 4 * (p))
#define WCD_PGD_TX_CFG(p)	(0x050 + (p))
#define WCD_PGD_INT_TX_EN0	0x032
#define WCD_TX_CH_START		128
#define WCD_CFILT_K_1800MV	24	/* wcd9xxx_resmgr_get_k_val, LDO_H at 3.0 V */

static const u8 wcd9330_mic_pairs[][2] = { { 1, 6 }, { 3, 4 } };

static void wcd9330_mic_power(struct wcd9330_codec *wcd, u8 line, bool on)
{
	struct regmap *rm = wcd->regmap;
	u16 ctl = line == 1 ? WCD_MICB_1_CTL : line == 6 ? WCD_MICB_4_CTL : WCD_MICB_3_CTL;
	u16 rbias = line == 1 ? WCD_MICB_1_INT_RBIAS : line == 6 ? WCD_MICB_4_INT_RBIAS :
				WCD_MICB_3_INT_RBIAS;
	u8 cfilt = line == 1 ? 0 : 2;	/* 3.10 msm8994.dtsi: bias 1 on cfilt 1, bias 3, 4 on cfilt 3 */

	if (on) {
		regmap_update_bits(rm, ctl, 0x60, cfilt << 5);
		regmap_write(rm, rbias, 0x24);
	}
	regmap_update_bits(rm, ctl, 0x80, on ? 0x80 : 0);
}

/* 3.10 tomtom_codec_enable_dmic: lines come in pairs that share one clock */
static void wcd9330_dmic_clock(struct wcd9330_codec *wcd, u8 line, bool on)
{
	struct regmap *rm = wcd->regmap;
	u8 en = line <= 2 ? 0x01 : line <= 4 ? 0x02 : 0x04;

	/* 4.8 MHz from 9.6: divider value 0 in each pair's field */
	if (on) {
		if (line <= 2)
			regmap_update_bits(rm, WCD_DMIC_B1_CTL, 0xe0, 0);
		else if (line <= 4)
			regmap_update_bits(rm, WCD_DMIC_B2_CTL, 0x0e, 0);
		else
			regmap_update_bits(rm, WCD_DMIC_B2_CTL, 0x70, 0);
	}
	regmap_update_bits(rm, WCD_DMIC_B1_CTL, en, on ? en : 0);
}

/* 3.10 tomtom_codec_enable_dec, dec mux and SLIM TX mux, decimator d = DMIC line d */
static void wcd9330_dec_on(struct wcd9330_codec *wcd, u8 d, u8 fs, u8 bit_sel)
{
	struct regmap *rm = wcd->regmap;
	u16 conn = WCD_CONN_TX_B1 + (d - 1) / 4;
	u8 shift = ((d - 1) % 4) * 2;
	u8 bit = BIT(d - 1);

	regmap_update_bits(rm, conn, 0x3 << shift, 0x1 << shift);
	/* DEC n on port n: 8 on the low nibble; sample width at bit 4 */
	regmap_update_bits(rm, WCD_CONN_TX_SB(d - 1), 0x0f, 0x08);
	regmap_update_bits(rm, WCD_CONN_TX_SB(d - 1), 0x3 << 4, bit_sel << 4);
	regmap_update_bits(rm, WCD_TX_CLK_FS(d), 0x07, fs);
	regmap_update_bits(rm, WCD_TX_DMIC_CTL(d), 0x07, 0);
	regmap_update_bits(rm, WCD_TX_VOL_CFG(d), 0x01, 0x01);
	regmap_update_bits(rm, WCD_CLK_TX_RESET_B1, bit, bit);
	regmap_update_bits(rm, WCD_CLK_TX_RESET_B1, bit, 0);
	/* high-pass filter on, at 150 Hz */
	regmap_update_bits(rm, WCD_TX_MUX_CTL(d), 0x30, 0x1 << 4);
	regmap_update_bits(rm, WCD_TX_MUX_CTL(d), 0x08, 0);
	regmap_update_bits(rm, WCD_CLK_TX_EN_B1, bit, bit);
	regmap_write(rm, WCD_TX_VOL_GAIN(d), wcd->mic_gain);
	regmap_update_bits(rm, WCD_TX_VOL_CFG(d), 0x01, 0);
}

static void wcd9330_dec_off(struct wcd9330_codec *wcd, u8 d)
{
	struct regmap *rm = wcd->regmap;
	u16 conn = WCD_CONN_TX_B1 + (d - 1) / 4;
	u8 shift = ((d - 1) % 4) * 2;
	u8 bit = BIT(d - 1);

	regmap_update_bits(rm, WCD_TX_VOL_CFG(d), 0x01, 0x01);
	regmap_update_bits(rm, WCD_CLK_TX_EN_B1, bit, 0);
	regmap_update_bits(rm, WCD_CONN_TX_SB(d - 1), 0x0f, 0);
	regmap_update_bits(rm, conn, 0x3 << shift, 0);
}

static void wcd9330_capture_off(struct wcd9330_codec *wcd)
{
	const u8 *pair = wcd9330_mic_pairs[wcd->capture_pair];
	struct regmap *rm = wcd->regmap;
	int i;

	if (!wcd->capture_on)
		return;
	wcd->capture_on = false;

	for (i = 0; i < 2; i++) {
		wcd9330_dec_off(wcd, pair[i]);
		wcd9330_dmic_clock(wcd, pair[i], false);
		wcd9330_mic_power(wcd, pair[i], false);
	}
	regmap_update_bits(rm, WCD_MICB_CFILT_1_CTL, 0x80, 0);
	regmap_update_bits(rm, WCD_MICB_CFILT_3_CTL, 0x80, 0);
	regmap_update_bits(rm, WCD_LDO_H_MODE_1, 0x80, 0);
	wcd9330_enable_mclk(wcd, false);
}

static int wcd9330_capture_power_on(struct wcd9330_codec *wcd, u8 fs, u8 bit_sel)
{
	const u8 *pair = wcd9330_mic_pairs[wcd->mic_pair];
	struct regmap *rm = wcd->regmap;
	int i, ret;

	ret = wcd9330_enable_mclk(wcd, true);
	if (ret)
		return ret;

	wcd->capture_pair = wcd->mic_pair;
	wcd->capture_on = true;

	/* 3.10 tomtom_handle_pdata: LDO_H at 3.0 V, filters at 1.8 V */
	regmap_update_bits(rm, WCD_LDO_H_MODE_1, 0x0c, 0x3 << 2);
	regmap_update_bits(rm, WCD_MICB_CFILT_1_VAL, 0xfc, WCD_CFILT_K_1800MV << 2);
	regmap_update_bits(rm, WCD_MICB_CFILT_3_VAL, 0xfc, WCD_CFILT_K_1800MV << 2);
	regmap_update_bits(rm, WCD_LDO_H_MODE_1, 0x80, 0x80);
	usleep_range(1000, 1100);
	regmap_update_bits(rm, WCD_MICB_CFILT_1_CTL, 0x80, 0x80);
	regmap_update_bits(rm, WCD_MICB_CFILT_3_CTL, 0x80, 0x80);

	for (i = 0; i < 2; i++)
		wcd9330_mic_power(wcd, pair[i], true);
	usleep_range(5000, 5100);
	for (i = 0; i < 2; i++) {
		wcd9330_dmic_clock(wcd, pair[i], true);
		wcd9330_dec_on(wcd, pair[i], fs, bit_sel);
	}
	return 0;
}

static int wcd9330_tx_hw_params(struct snd_pcm_substream *substream,
				struct snd_pcm_hw_params *params,
				struct snd_soc_dai *dai)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(dai->component);
	struct wcd9330_dai_data *data = &wcd->dai[dai->id];
	struct slim_stream_config *cfg = &data->sconfig;
	const u8 *pair;
	u16 payload = 0;
	u8 fs, bit_sel;
	int i, ret;

	switch (params_rate(params)) {
	case 8000:
		fs = 0;
		break;
	case 16000:
		fs = 1;
		break;
	case 32000:
		fs = 2;
		break;
	case 48000:
		fs = 3;
		break;
	case 96000:
		fs = 4;
		break;
	default:
		return -EINVAL;
	}
	bit_sel = params_width(params) == 16 ? 0x2 : 0x0;

	wcd9330_slim_stop(data);
	if (data->sruntime) {
		slim_stream_free(data->sruntime);
		data->sruntime = NULL;
	}
	wcd9330_capture_off(wcd);

	ret = wcd9330_capture_power_on(wcd, fs, bit_sel);
	if (ret)
		return ret;

	pair = wcd9330_mic_pairs[wcd->capture_pair];
	kfree(cfg->chs);
	cfg->chs = kcalloc(2, sizeof(unsigned int), GFP_KERNEL);
	if (!cfg->chs) {
		ret = -ENOMEM;
		goto err;
	}
	cfg->ch_count = 2;
	cfg->direction = SNDRV_PCM_STREAM_CAPTURE;
	cfg->rate = params_rate(params);
	cfg->bps = params_width(params);
	cfg->port_mask = 0;
	for (i = 0; i < 2; i++) {
		u8 port = pair[i] - 1;

		payload |= BIT(port);
		cfg->port_mask |= BIT(port);
		cfg->chs[i] = WCD_TX_CH_START + port;
	}
	for (i = 0; i < 2; i++) {
		u8 port = pair[i] - 1;
		unsigned int val = 0;

		regmap_write(wcd->if_regmap, WCD_PGD_TX_MULTI_0(port), payload & 0xff);
		regmap_write(wcd->if_regmap, WCD_PGD_TX_MULTI_1(port), payload >> 8);
		regmap_write(wcd->if_regmap, WCD_PGD_TX_CFG(port),
			     TOMTOM_SLAVE_PORT_WATER_MARK_VAL);
		regmap_read(wcd->if_regmap, WCD_PGD_INT_TX_EN0 + port / 8, &val);
		regmap_write(wcd->if_regmap, WCD_PGD_INT_TX_EN0 + port / 8,
			     val | BIT(port % 8));
	}

	data->sruntime = slim_stream_allocate(wcd->slim, "WCD9330-SLIM-TX");
	if (IS_ERR(data->sruntime)) {
		ret = PTR_ERR(data->sruntime);
		data->sruntime = NULL;
		goto err;
	}
	/*
	 * 3.10 connects and activates the channel in the AIF's POST_PMU, once the DSP's port has
	 * started: wcd9330_trigger does it here. Playback goes the other way round.
	 */
	return 0;
err:
	wcd9330_capture_off(wcd);
	return ret;
}

static int wcd9330_tx_hw_free(struct snd_pcm_substream *substream,
			      struct snd_soc_dai *dai)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(dai->component);
	struct wcd9330_dai_data *data = &wcd->dai[dai->id];

	wcd9330_slim_stop(data);
	if (data->sruntime) {
		slim_stream_free(data->sruntime);
		data->sruntime = NULL;
	}
	wcd9330_capture_off(wcd);
	return 0;
}

static int wcd9330_tx_get_channel_map(const struct snd_soc_dai *dai,
				      unsigned int *tx_num, unsigned int *tx_slot,
				      unsigned int *rx_num, unsigned int *rx_slot)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(dai->component);

	if (!tx_slot || !tx_num)
		return -EINVAL;
	/* The card asks before this stream's hw_params has run. */
	tx_slot[0] = WCD_TX_CH_START + wcd9330_mic_pairs[wcd->mic_pair][0] - 1;
	tx_slot[1] = WCD_TX_CH_START + wcd9330_mic_pairs[wcd->mic_pair][1] - 1;
	*tx_num = 2;
	return 0;
}

static const struct snd_soc_dai_ops wcd9330_tx_dai_ops = {
	.hw_params = wcd9330_tx_hw_params,
	.hw_free = wcd9330_tx_hw_free,
	.trigger = wcd9330_trigger,
	.set_channel_map = wcd9330_set_channel_map,
	.get_channel_map = wcd9330_tx_get_channel_map,
};

"""

CONTROLS = r"""static const char * const wcd9330_mic_text[] = { "DMIC1 DMIC6", "DMIC3 DMIC4" };
static SOC_ENUM_SINGLE_EXT_DECL(wcd9330_mic_enum, wcd9330_mic_text);

static int wcd9330_mic_get(struct snd_kcontrol *kc, struct snd_ctl_elem_value *uc)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(snd_kcontrol_chip(kc));

	uc->value.enumerated.item[0] = wcd->mic_pair;
	return 0;
}

static int wcd9330_mic_put(struct snd_kcontrol *kc, struct snd_ctl_elem_value *uc)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(snd_kcontrol_chip(kc));
	unsigned int v = uc->value.enumerated.item[0];

	if (v >= ARRAY_SIZE(wcd9330_mic_text))
		return -EINVAL;
	if (v == wcd->mic_pair)
		return 0;
	wcd->mic_pair = v;	/* from the next time the stream opens */
	return 1;
}

static int wcd9330_mic_gain_get(struct snd_kcontrol *kc, struct snd_ctl_elem_value *uc)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(snd_kcontrol_chip(kc));

	uc->value.integer.value[0] = wcd->mic_gain;
	return 0;
}

static int wcd9330_mic_gain_put(struct snd_kcontrol *kc, struct snd_ctl_elem_value *uc)
{
	struct wcd9330_codec *wcd = snd_soc_component_get_drvdata(snd_kcontrol_chip(kc));
	long v = uc->value.integer.value[0];

	if (v < 0 || v > 40)
		return -EINVAL;
	if (v == wcd->mic_gain)
		return 0;
	wcd->mic_gain = v;
	return 1;
}

"""

EDITS = [
    ("\tAIF1_PB,\n\tNUM_CODEC_DAIS,", "\tAIF1_PB,\n\tAIF1_CAP,\n\tNUM_CODEC_DAIS,"),
    ("\tint num_rx_port;\n};",
     "\tint num_rx_port;\n\tbool capture_on;\n\tu8 capture_pair;\n\tu8 mic_pair;\n\tu8 mic_gain;\n};"),
    ("static const struct snd_kcontrol_new wcd9330_snd_controls[] = {\n",
     CONTROLS + "static const struct snd_kcontrol_new wcd9330_snd_controls[] = {\n"
     '\tSOC_ENUM_EXT("Mic Select", wcd9330_mic_enum, wcd9330_mic_get, wcd9330_mic_put),\n'
     '\tSOC_SINGLE_EXT("Mic Gain", SND_SOC_NOPM, 0, 40, 0, wcd9330_mic_gain_get, wcd9330_mic_gain_put),\n'),
    ("static const struct snd_soc_dapm_widget wcd9330_dapm_widgets[] = {\n",
     "static const struct snd_soc_dapm_widget wcd9330_dapm_widgets[] = {\n"
     '\tSND_SOC_DAPM_AIF_OUT("AIF1 CAP", "AIF1 Capture", 0, SND_SOC_NOPM, 0, 0),\n'
     '\tSND_SOC_DAPM_INPUT("MIC"),\n'),
    ("static const struct snd_soc_dapm_route wcd9330_audio_map[] = {\n",
     "static const struct snd_soc_dapm_route wcd9330_audio_map[] = {\n"
     '\t{ "AIF1 CAP", NULL, "MIC" },\n'),
    ("\t\t.ops = &wcd9330_dai_ops,\n\t},\n};",
     "\t\t.ops = &wcd9330_dai_ops,\n\t},\n\t{\n"
     '\t\t.name = "tomtom_tx1",\n\t\t.id = AIF1_CAP,\n\t\t.capture = {\n'
     '\t\t\t.stream_name = "AIF1 Capture",\n\t\t\t.rates = WCD9330_RATES,\n'
     "\t\t\t.formats = WCD9330_FORMATS,\n\t\t\t.rate_min = 8000,\n\t\t\t.rate_max = 96000,\n"
     "\t\t\t.channels_min = 2,\n\t\t\t.channels_max = 2,\n\t\t},\n"
     "\t\t.ops = &wcd9330_tx_dai_ops,\n\t},\n};"),
    # after the playback ops and what they use, before the DAIs
    ("static struct snd_soc_dai_driver wcd9330_dai[] = {\n",
     FUNCTIONS + "static struct snd_soc_dai_driver wcd9330_dai[] = {\n"),
]


def main() -> None:
    path = Path(sys.argv[1]) / CODEC
    text = path.read_text()
    for old, new in EDITS:
        if text.count(old) != 1:
            sys.exit(f"patch-wcd-capture: {CODEC}: not found once: {old[:60]!r}")
        text = text.replace(old, new)
    path.write_text(text)
    print("patch-wcd-capture: the microphones")


if __name__ == "__main__":
    main()
