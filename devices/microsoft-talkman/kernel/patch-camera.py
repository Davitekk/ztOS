#!/usr/bin/env python3
"""The Lumia 950's cameras: camss on this chip, and the nodes that describe them.

camss-msm8994.patch adds the chip to the camss driver; camera-talkman.dtsi goes at the
end of the phone's device tree.

Usage: patch-camera.py <kernel source>
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DTS = "arch/arm64/boot/dts/qcom/msm8992-msft-lumia-octagon-talkman.dts"
# camss starts every subdev from the video node back to the sensor. These sensors are
# three subdevs (scaler, binner, pixel array), and ccs only takes s_stream at the first:
# the pixel array answers -EINVAL. The first subdev that isn't camss's own is the last.
VIDEO = "drivers/media/platform/qcom/camss/camss-video.c"
START = """		ret = v4l2_subdev_call(subdev, video, s_stream, 1);
		if (ret < 0 && ret != -ENOIOCTLCMD)
			goto error;
"""
STOP = """			dev_err(video->camss->dev, "Video pipeline stop failed: %d\\n", ret);
			return;
		}
"""
BREAK = """
		if (strncmp(entity->name, "msm_", 4))
			break;
"""
# Qualcomm's msm_csiphy.c does this for "qcom,csiphy-v3.1.1", the 20 nm PHY of this chip
# (is_3_1_20nm_hw): each lane's position and impedance. Without it, the receiver sees
# nothing while the sensor streams.
PHY = "drivers/media/platform/qcom/camss/camss-csiphy-2ph-1-0.c"
PHY_END = """		writel_relaxed(0x3f, csiphy->base +
			       CAMSS_CSI_PHY_INTERRUPT_CLEARn(l));
	}
"""
# The camera IOMMU: this phone's secure world refuses to set it up (restore_sec_cfg(19, 0) is
# -EINVAL), and with Linux mapping its streams the write master only overflows, no fault
# reported. Unmapped, the VFE writes to physical addresses, so its buffers are contiguous.
CONTIG = (
    ("#include <media/videobuf2-dma-sg.h>", "#include <media/videobuf2-dma-contig.h>"),
    ("""	struct sg_table *sgt;
	unsigned int i;
""", """	unsigned int i;
"""),
    ("""		sgt = vb2_dma_sg_plane_desc(vb, i);
		if (!sgt)
			return -EFAULT;

		buffer->addr[i] = sg_dma_address(sgt->sgl);
""", """		buffer->addr[i] = vb2_dma_contig_plane_dma_addr(vb, i);
"""),
    ("q->mem_ops = &vb2_dma_sg_memops;", "q->mem_ops = &vb2_dma_contig_memops;"),
)
KCONFIG = "drivers/media/platform/qcom/camss/Kconfig"
SELECT_SG = """	select VIDEOBUF2_DMA_SG
"""
SELECT_CONTIG = """	select VIDEOBUF2_DMA_CONTIG
"""
# The bus bridge between the VFE and memory, as in Qualcomm's msm8992-camera.dtsi
# (vbif-regs, vbif-settings). VFE1 shares it, and one region can only be claimed once.
VBIF = "drivers/media/platform/qcom/camss/camss-vfe-vbif.c"
VBIF_START = """int vfe_vbif_apply_settings(struct vfe_device *vfe)
{
"""
VBIF_8992 = """	if (vfe->camss->res->version == CAMSS_8x94) {
		vfe_vbif_write_reg(vfe, 0x004, 0x00000001);
		vfe_vbif_write_reg(vfe, 0x0b0, 0x00100000);
		vfe_vbif_write_reg(vfe, 0x0b4, 0x00001000);
		vfe_vbif_write_reg(vfe, 0x0b8, 0x10000010);
		vfe_vbif_write_reg(vfe, 0x0c0, 0x10000010);
		vfe_vbif_write_reg(vfe, 0x0c4, 0x10100000);
		vfe_vbif_write_reg(vfe, 0x0c8, 0x00101000);
		vfe_vbif_write_reg(vfe, 0x124, 0x00000003);
		return 0;
	}

"""
CAMSS = "drivers/media/platform/qcom/camss/camss.c"
VFE_RES = "vfe_res_8x94[] = {"
VFE_LINE = """			.line_num = 3,
"""
VFE_VBIF = """			.has_vbif = true,
			.vbif_name = "vfe0_vbif",
"""
# Qualcomm's msm8992-camera.dtsi runs the VFE at 320 MHz. The driver's choice for RDI, a
# small share of the pixel rate, gave 80 MHz here and the write master overflowed.
VFE_RATES = """				{ 75000000, 100000000, 300000000,
				  320000000, 480000000, 600000000 },
"""
VFE_RATES_8992 = """				{ 320000000, 480000000, 600000000 },
"""
# ISPIF as on 8x96, which also has two VFEs: the 8x16 handler the branch used only clears
# VFE0's status, and its format list has no 14-bit, which the rear camera needs.
ISPIF = "drivers/media/platform/qcom/camss/camss-ispif.c"
ISPIF_EDITS = (
    ("""		    camss->res->version == CAMSS_8x39 ||
			camss->res->version == CAMSS_8x94) {
			ispif->line[i].formats = ispif_formats_8x16;
""", """		    camss->res->version == CAMSS_8x39) {
			ispif->line[i].formats = ispif_formats_8x16;
"""),
    ("""			   camss->res->version == CAMSS_660) {
			ispif->line[i].formats = ispif_formats_8x96;
""", """			   camss->res->version == CAMSS_660 ||
			   camss->res->version == CAMSS_8x94) {
			ispif->line[i].formats = ispif_formats_8x96;
"""),
    ("""	    camss->res->version == CAMSS_8x39 ||
		camss->res->version == CAMSS_8x94)
		ret = devm_request_irq(dev, ispif->irq, ispif_isr_8x16,
""", """	    camss->res->version == CAMSS_8x39)
		ret = devm_request_irq(dev, ispif->irq, ispif_isr_8x16,
"""),
    ("""		 camss->res->version == CAMSS_660)
		ret = devm_request_irq(dev, ispif->irq, ispif_isr_8x96,
""", """		 camss->res->version == CAMSS_660 ||
		 camss->res->version == CAMSS_8x94)
		ret = devm_request_irq(dev, ispif->irq, ispif_isr_8x96,
"""),
)
# The front sensor sends 2608 pixels a row for its 2600 (3260 bytes, padded to 3264), so at
# the driver's 8-byte rows a frame ran past the end of its buffer; 16 leaves room. Rows in
# memory are what was sent: 3264 bytes on the front, 9352 on the rear, whatever
# bytesperline says.
VFE = "drivers/media/platform/qcom/camss/camss-vfe.c"
RDI_ALIGN = """static int vfe_bpl_align_rdi(struct vfe_device *vfe)
{
	int ret = 8;
"""
RDI_ALIGN_8992 = """static int vfe_bpl_align_rdi(struct vfe_device *vfe)
{
	int ret = vfe->camss->res->version == CAMSS_8x94 ? 16 : 8;
"""
# msm_isp44.c sets the burst length in frame based mode too (VFE44_BURST_LEN); it was 0.
VFE41 = "drivers/media/platform/qcom/camss/camss-vfe-4-1.c"
FRAME_BASED = """static void vfe_wm_frame_based(struct vfe_device *vfe, u8 wm, u8 enable)
{
"""
FRAME_BURST = """	writel_relaxed(enable ? 0x3 : 0, vfe->base +
		       VFE_0_BUS_IMAGE_MASTER_n_WR_BUFFER_CFG(wm));

"""
PHY_INCLUDE = """#include "camss-csiphy.h"
"""
CAMSS_INCLUDE = """#include "camss.h"
"""
PHY_20NM = """
	if (csiphy->camss->res->version == CAMSS_8x94) {
		u8 lane = 0;

		for (i = 0; i < 5; i++) {
			if (!(lane_mask & BIT(i)))
				continue;
			if (i > 1)
				val = 0x8 | (c->num_data - lane) << 4;
			else
				val = i == 1 ? 0x4 : 0;
			writel_relaxed(val, csiphy->base + 0x28 + 0x40 * i);
			writel_relaxed(0x17, csiphy->base + 0x1c + 0x40 * i);
			lane++;
		}
	}
"""


def main() -> None:
    source = Path(sys.argv[1])
    subprocess.run(["patch", "-p1", "-s", "-f", "-i", str(HERE / "camss-msm8994.patch")],
                   cwd=source, check=True)
    path = source / VIDEO
    text = path.read_text()
    for anchor, stop in ((START, BREAK), (STOP, BREAK)):
        if text.count(anchor) != 1:
            sys.exit(f"patch-camera: {VIDEO}: anchor not found once: {anchor!r}")
        text = text.replace(anchor, anchor + stop)
    path.write_text(text)
    path = source / VIDEO
    text = path.read_text()
    for old, new in CONTIG:
        if text.count(old) != 1:
            sys.exit(f"patch-camera: {VIDEO}: not found once: {old!r}")
        text = text.replace(old, new)
    path.write_text(text)
    path = source / KCONFIG
    path.write_text(path.read_text().replace(SELECT_SG, SELECT_SG + SELECT_CONTIG, 1))
    path = source / VBIF
    text = path.read_text()
    if text.count(VBIF_START) != 1:
        sys.exit(f"patch-camera: {VBIF}: vfe_vbif_apply_settings not found once")
    path.write_text(text.replace(VBIF_START, VBIF_START + VBIF_8992))
    path = source / CAMSS
    head, resources = path.read_text().split(VFE_RES, 1)
    resources = resources.replace(VFE_RATES, VFE_RATES_8992, 2)
    path.write_text(head + VFE_RES + resources.replace(VFE_LINE, VFE_LINE + VFE_VBIF, 1))
    path = source / ISPIF
    text = path.read_text()
    for old, new in ISPIF_EDITS:
        if text.count(old) != 1:
            sys.exit(f"patch-camera: {ISPIF}: not found once: {old!r}")
        text = text.replace(old, new)
    path.write_text(text)
    path = source / VFE
    text = path.read_text()
    if text.count(RDI_ALIGN) != 1:
        sys.exit(f"patch-camera: {VFE}: vfe_bpl_align_rdi not found once")
    path.write_text(text.replace(RDI_ALIGN, RDI_ALIGN_8992))
    path = source / VFE41
    text = path.read_text()
    if text.count(FRAME_BASED) != 1:
        sys.exit(f"patch-camera: {VFE41}: vfe_wm_frame_based not found once")
    path.write_text(text.replace(FRAME_BASED, FRAME_BASED + FRAME_BURST))
    path = source / PHY
    text = path.read_text()
    if text.count(PHY_END) != 1:
        sys.exit(f"patch-camera: {PHY}: end of csiphy_lanes_enable not found once")
    text = text.replace(PHY_END, PHY_END + PHY_20NM)
    path.write_text(text.replace(PHY_INCLUDE, PHY_INCLUDE + CAMSS_INCLUDE, 1))
    path = source / DTS
    path.write_text(path.read_text() + "\n" + (HERE / "camera-talkman.dtsi").read_text())
    print("patch-camera: camss on this chip, the rear and front cameras in the device tree")


if __name__ == "__main__":
    main()
