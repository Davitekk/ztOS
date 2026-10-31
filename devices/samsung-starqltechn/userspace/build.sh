#!/bin/sh
# Build and install the Qualcomm userspace of sources.txt, inside the phone's
# own root (layer.sh runs it there under qemu, from /usr/src/ztos-qcom where
# fetch.sh's checked tarballs were put). Each the way Alpine builds it for
# postmarketOS. tqftpserv and 81voltd keep their own systemd units; rmtfs,
# hexagonrpcd, msm-modem-uim-selection and q6voiced have none for systemd here,
# or none that fits this phone, and theirs are in overlay/.
#
#   qrtr        libqrtr (the kernel has the name service: no qrtr-ns)
#   rmtfs       the modem's remote file system: its EFS copies on modemst1/2,
#               fsg, fsc, served read-only (-r: never written back)
#   tqftpserv   the TFTP server the modem and ADSP fetch their files from
#   hexagonrpcd the FastRPC host for the sensor DSP (SLPI) and the ADSP
#   msm-modem   msm-modem-uim-selection: picks the SIM application at start
#   q6voiced    opens the DSP's voice path while a call is up (call audio)
#   81voltd     the IMS data service the modem asks for (VoLTE)
#
# Pin protection domains are served by the kernel (qcom_pd_mapper), so there
# is no pd-mapper here.
set -eu
S=/usr/src/ztos-qcom
B=$S/build
rm -rf "$B"
mkdir -p "$B"
cd "$B"
for t in "$S"/*.tar.gz; do
	tar -xzf "$t"
done

mesonb() {      # <dir> [options...]: configure, build and install with meson
	d=$1; shift
	(cd "$d" && meson setup --prefix=/usr --libexecdir=lib --buildtype=release \
		--wrap-mode=nodownload "$@" output > /dev/null &&
		meson compile -C output > /dev/null && meson install --no-rebuild -C output > /dev/null)
	echo "qcom: $d installed"
}

mesonb qrtr-1.2 -Dqrtr-ns=disabled -Dsystemd-service=disabled
(cd rmtfs-1.3 && make -s rmtfs && install -Dm755 rmtfs /usr/bin/rmtfs)
echo "qcom: rmtfs installed"
mesonb tqftpserv-1.3 -Dsystemd-unit-prefix=/usr/lib/systemd/system
mesonb hexagonrpc-0.4.0
mesonb msm-modem-13 -Duim-selection=true -Dwwan-port=false -Ddownstream=false \
	-Dopenrc=false -Dsystemd=false
mesonb q6voiced-0.3.1 -Dopenrc=disabled -Dsystemd=disabled
mesonb 81voltd-v1.2.0
# OpenRC's leftovers, where a build has no switch for them
rm -f /etc/init.d/81voltd /etc/init.d/tqftpserv /etc/conf.d/msm-modem-uim-selection
rmdir /etc/init.d /etc/conf.d 2> /dev/null || true
ldconfig
cd /
rm -rf "$B"
