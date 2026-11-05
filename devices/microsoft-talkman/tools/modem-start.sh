#!/bin/bash
# modem-start.sh: start the modem by hand, for whoever carries on with it. Run as root on the phone.
#
# Needs in /usr/lib/firmware: qcdsp1v28992.mbn, qcdsp28992.mbn (Android4Lumia950/firmware-microsoft-talkman,
# commit e9e9fac86db9dfd0a1992062987cfcbfd92403c7), and rmtfs on the PATH (github.com/linux-msm/qrtr, then
# github.com/linux-msm/rmtfs).
#
# MODEM_FS1, FS2, FSC and FSG hold the phone's identity and its radio calibration. They are only ever
# read, once, to private files, and rmtfs runs on those. Never give it -P, which writes to the partitions.
#
# Where it stands: the modem boots, its router services come up, and DATA1 to DATA4 answer AT commands
# (see at()). AT+CFUN=1 is accepted, but AT+CPIN? stays at "SIM busy" and the SIM's pins stay low. DMS,
# NAS, WDS, WMS and UIM never appear on the router, and no QMUX channel (DATA5_CNTL, DATA40_CNTL) opens,
# even after a Data Port Mapper open-port request. A guess at why: the modem waits for the phone's side of
# IPA, whose control service it does offer. This chip's IPA is v2.0, and the kernel's driver starts at v3.0.
set -eu
D=/var/lib/rmtfs
R=/sys/class/remoteproc/remoteproc1

install -d -m700 "$D"
for p in "MODEM_FS1 modem_fs1" "MODEM_FS2 modem_fs2" "MODEM_FSC modem_fsc" "MODEM_FSG modem_fsg"; do
	set -- $p
	if [ ! -s "$D/$2" ]; then
		dd if="/dev/disk/by-partlabel/$1" of="$D/$2" bs=1M iflag=fullblock status=none
		chmod 600 "$D/$2"
	fi
done
sync

pgrep -x rmtfs > /dev/null || (nohup rmtfs -o "$D" > /var/tmp/rmtfs.log 2>&1 &)
sleep 1
[ "$(cat "$R/state")" = running ] || echo start > "$R/state"
sleep 30
cat "$R/state"
qrtr-lookup | awk '$4 == 0'

# An AT port, as /dev/rpmsgN
at() {
	d=/sys/bus/rpmsg/devices/remoteproc1:smd-edge.$1.-1.-1
	echo rpmsg_chrdev > "$d/driver_override"
	echo "$(basename "$d")" > /sys/bus/rpmsg/drivers/rpmsg_chrdev/bind
	ls "$d/rpmsg"
}
at DATA1
