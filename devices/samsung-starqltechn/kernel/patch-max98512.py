#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""The MAX98512 amplifier pair (Samsung's downstream driver in sdm845-mainline):
a new "One Stop Mode" at once, also while the amps play.

The mode says which speaker plays: Stereo (media, both), Mono Left (a call
on the earpiece), Mono Right (a call on the bottom speaker). The driver only
stores it, and applies it the next time a stream starts. A call's voice path
often starts before the call's profile sets Mono Left, and then the call
played in Stereo, out of the bottom speaker; the speakerphone switch in a
call did nothing at all. Now, if an amp is on, the mode is applied there and
then, as at a stream's start (max98512_spk_enable).

Asserted, so a changed upstream file fails instead of silently building
without it. Takes the kernel source directory as its only argument.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "sound/soc/codecs/max98512-downstream/max98512.c"
src = path.read_text()
old = ("\tosm = osm < 0 ? 0 : osm;\n"
       "\tif (osm < MAX98512_OSM_MAX && pdata->osm != osm)\n"
       "\t\tpdata->osm = osm;\n")
new = ("\tosm = osm < 0 ? 0 : osm;\n"
       "\tif (osm < MAX98512_OSM_MAX && pdata->osm != osm) {\n"
       "\t\tunsigned int on_l = 0, on_r = 0;\n"
       "\n"
       "\t\tpdata->osm = osm;\n"
       "\t\t/* ztOS: playing now: the new mode at once (patch-max98512.py) */\n"
       "\t\tmax98512_wrapper_read(max98512, MAX98512L, MAX98512_R0400_GLOBAL_SHDN, &on_l);\n"
       "\t\tif (max98512->mono_stereo)\n"
       "\t\t\tmax98512_wrapper_read(max98512, MAX98512R, MAX98512_R0400_GLOBAL_SHDN, &on_r);\n"
       "\t\tif ((on_l | on_r) & MAX98512_GLOBAL_EN_MASK)\n"
       "\t\t\tmax98512_spk_enable(max98512, 1);\n"
       "\t}\n")
if new not in src:
    assert src.count(old) == 1, "max98512.c changed: look at One Stop Mode again"
    # max98512_spk_enable is defined above the control's handler
    assert src.index("static void max98512_spk_enable(") < src.index(old)
    src = src.replace(old, new)
    path.write_text(src)
    print("max98512.c: One Stop Mode applied at once while playing")
else:
    print("max98512.c: already patched")
