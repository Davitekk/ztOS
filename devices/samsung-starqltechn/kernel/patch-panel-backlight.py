#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""A backlight for the S6E3HA8 (AMB577PX01) panel, which upstream's driver
does not have: the Galaxy S9's own panel, the same on the Exynos and the
Snapdragon phones.

The panel takes no DCS brightness (0x51). Its own dimming is AOR, register
B1, behind the level-2 key and latched by F7 03, which upstream's on
sequence already writes once at full brightness (B1 00 0C, "AID 0%"). The
levels are Samsung's star_a3_s0_aor_table, 573 of them, 0 the dimmest, as
the Exynos S9's kernel drives the same panel: the table is taken from
kernel/s9p-decon-backlight.patch in this repository, so both S9s keep one.
The backlight is named s9p-panel like the Exynos S9's, and ztMETRO drives it
the same way (ztOSIAL Display1 mode "aor": four AOR bands, the rest of the
way down darkened on the GPU).

Also from the Exynos S9: the panel's self mask (an image in its side memory
over the rounded corners) is switched off on every power-on (7A 00), so that
after a sleep it cannot paint dark patches along the top and the bottom.

Every edit asserts its anchor; idempotent. Takes the kernel source
directory as its only argument.
"""
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
here = Path(__file__).resolve().parent
repo = here.parents[2]
DRV = src / "drivers/gpu/drm/panel/panel-samsung-s6e3ha8.c"
s = DRV.read_text()
MARK = "/* ztOS: AOR backlight */"
if MARK in s:
    print(f"{DRV.name}: already patched")
    sys.exit(0)

# the table, from the Exynos S9's patch
patch = (repo / "kernel/s9p-decon-backlight.patch").read_text()
m = re.search(r"^\+static const u16 s9p_aor_table\[S9P_BL_LEVELS\] = \{\n(.*?)^\+\};", patch, re.M | re.S)
assert m, "kernel/s9p-decon-backlight.patch: no s9p_aor_table"
values = re.findall(r"0x[0-9a-fA-F]{4}", m.group(1))
levels = int(re.search(r"^\+#define S9P_BL_LEVELS\s+(\d+)", patch, re.M).group(1))
assert len(values) == levels == 573, f"AOR table: {len(values)} values for {levels} levels"
assert values[-1].lower() == "0x000c", "the brightest AOR level is not the on sequence's 00 0C"
rows = ["\t" + ", ".join(values[i:i + 8]) + "," for i in range(0, len(values), 8)]

def sub(old, new, count=1):
    global s
    assert s.count(old) == count, f"{DRV.name}: {old!r} found {s.count(old)} times"
    s = s.replace(old, new)

sub("#include <linux/delay.h>\n", "#include <linux/backlight.h>\n#include <linux/delay.h>\n")

sub("\tstruct regulator_bulk_data *supplies;\n};\n",
    "\tstruct regulator_bulk_data *supplies;\n"
    "\tstruct backlight_device *bl;\n"
    "\tbool on;\t\t/* initialised and taking commands */\n};\n")

TABLE = MARK + """
/*
 * Samsung's star_a3_s0_aor_table (via the Exynos S9's
 * kernel/s9p-decon-backlight.patch): the value of register B1 for each of
 * 573 levels, 0 the dimmest, 572 the on sequence's "AID 0%%".
 */
#define S6E3HA8_BL_LEVELS	%d

static const u16 s6e3ha8_aor_table[S6E3HA8_BL_LEVELS] = {
%s
};

static int s6e3ha8_send_brightness(struct s6e3ha8 *priv, unsigned int level)
{
	struct mipi_dsi_multi_context ctx = { .dsi = priv->dsi };
	u8 b1[3] = { 0xb1 };
	u16 aor;

	if (level >= S6E3HA8_BL_LEVELS)
		level = S6E3HA8_BL_LEVELS - 1;
	aor = s6e3ha8_aor_table[level];
	b1[1] = aor >> 8;
	b1[2] = aor & 0xff;

	s6e3ha8_test_key_on_lvl2(&ctx);
	mipi_dsi_dcs_write_buffer_multi(&ctx, b1, sizeof(b1));
	mipi_dsi_dcs_write_seq_multi(&ctx, 0xf7, 0x03);	/* latch on the next frame */
	s6e3ha8_test_key_off_lvl2(&ctx);

	return ctx.accum_err;
}

static int s6e3ha8_bl_update_status(struct backlight_device *bl)
{
	struct s6e3ha8 *priv = bl_get_data(bl);

	/* off, or not yet initialised: the level goes out at the next power-on */
	if (!priv->on || backlight_is_blank(bl))
		return 0;
	return s6e3ha8_send_brightness(priv, backlight_get_brightness(bl));
}

/* No .get_brightness: a DCS read on this host can take the pipeline down. */
static const struct backlight_ops s6e3ha8_bl_ops = {
	.update_status = s6e3ha8_bl_update_status,
};

""" % (levels, "\n".join(rows))

sub("static void s6e3ha8_amb577px01_wqhd_reset(struct s6e3ha8 *priv)\n",
    TABLE + "static void s6e3ha8_amb577px01_wqhd_reset(struct s6e3ha8 *priv)\n")

# the self mask off, right after sleep-out
sub("\tmipi_dsi_dcs_exit_sleep_mode_multi(&ctx);\n\tusleep_range(5000, 6000);\n",
    "\tmipi_dsi_dcs_exit_sleep_mode_multi(&ctx);\n\tusleep_range(5000, 6000);\n\n"
    "\t/* the self mask off (the Exynos S9's self_mask_dis): its image does not\n"
    "\t * survive a sleep, and the mask would then darken the top and bottom */\n"
    "\ts6e3ha8_test_key_on_lvl2(&ctx);\n"
    "\tmipi_dsi_dcs_write_seq_multi(&ctx, 0x7a, 0x00);\n"
    "\ts6e3ha8_test_key_off_lvl2(&ctx);\n")

# on: initialised, then the level the backlight holds; off before sleeping
sub("\tmipi_dsi_dcs_set_display_on_multi(&ctx);\n\ts6e3ha8_test_key_off_lvl1(&ctx);\n\n\treturn ctx.accum_err;\n}\n",
    "\tmipi_dsi_dcs_set_display_on_multi(&ctx);\n\ts6e3ha8_test_key_off_lvl1(&ctx);\n"
    "\tif (ctx.accum_err)\n\t\treturn ctx.accum_err;\n\n"
    "\tpriv->on = true;\n"
    "\tif (priv->bl && !backlight_is_blank(priv->bl))\n"
    "\t\treturn s6e3ha8_send_brightness(priv, backlight_get_brightness(priv->bl));\n"
    "\treturn 0;\n}\n")
sub("\tstruct mipi_dsi_multi_context ctx = { .dsi = dsi };\n\n\ts6e3ha8_test_key_on_lvl1(&ctx);\n\tmipi_dsi_dcs_set_display_off_multi(&ctx);\n",
    "\tstruct mipi_dsi_multi_context ctx = { .dsi = dsi };\n\n\tpriv->on = false;\n"
    "\ts6e3ha8_test_key_on_lvl1(&ctx);\n\tmipi_dsi_dcs_set_display_off_multi(&ctx);\n")

# registered before the panel, like the panels with a DCS backlight
sub("\tpriv->panel.prepare_prev_first = true;\n\n\tdrm_panel_add(&priv->panel);\n",
    "\tpriv->panel.prepare_prev_first = true;\n\n"
    "\t{\n"
    "\t\tconst struct backlight_properties props = {\n"
    "\t\t\t.type = BACKLIGHT_RAW,\n"
    "\t\t\t.max_brightness = S6E3HA8_BL_LEVELS - 1,\n"
    "\t\t\t/* what the on sequence sets (AID 0%) */\n"
    "\t\t\t.brightness = S6E3HA8_BL_LEVELS - 1,\n"
    "\t\t\t.scale = BACKLIGHT_SCALE_NON_LINEAR,\n"
    "\t\t};\n\n"
    "\t\t/* the Exynos S9's name: ztMETRO knows how to drive it */\n"
    "\t\tpriv->bl = devm_backlight_device_register(dev, \"s9p-panel\", dev, priv,\n"
    "\t\t\t\t\t\t\t  &s6e3ha8_bl_ops, &props);\n"
    "\t\tif (IS_ERR(priv->bl))\n"
    "\t\t\treturn dev_err_probe(dev, PTR_ERR(priv->bl), \"no backlight\\n\");\n"
    "\t}\n\n"
    "\tdrm_panel_add(&priv->panel);\n")

DRV.write_text(s)
print(f"{DRV.name}: AOR backlight (s9p-panel, {levels} levels) and self mask off")
