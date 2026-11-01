#!/bin/bash
# Keep the phone's data across a ztOS upgrade. A new ztOS version is a new
# root image (ztOS's own parts are built into it, so ztos-update's pacman
# cannot bring them), and flash-root.sh writes the whole of USERDATA: save
# what is the user's first, then put it back on the new system.
#
#   devices/samsung-starqltechn/scripts/upgrade.sh save [file]       the old system, booted
#   devices/samsung-starqltechn/scripts/upgrade.sh restore <file>    the new one, after its first boot
#
# An upgrade, start to end:
#   1. upgrade.sh save
#   2. in TWRP: flash-root.sh <root-chunks>, then flash.sh BOOT <boot image>
#   3. boot ztOS and wait for the lock screen (the first boot grows the
#      filesystem and sets up the user)
#   4. upgrade.sh restore backups/starqltechn/<file>; the phone reboots
#
# Kept: every home (settings, files, Android's apps and their data), Wi-Fi
# networks, Bluetooth pairings, calls and messages, the access point, the
# learned performance and sensor state, the clock's RTC offset, the SSH host
# keys, the time zone and
# the user's password. Waydroid's images too, unless the new system already
# has its own. Not kept: packages installed with pacman (listed at the end,
# to install again) and the rest of the system, which is the new version's.
# Both systems must have the same user (the installer's --user).
#
# The file holds Wi-Fi passwords and messages: it stays in backups/ (not in
# the repository). Over the USB link, ssh to zerone@172.16.42.1 (ZTOS_PHONE
# and ZTOS_SSH_PORT for others); the password is asked once, for ssh and sudo.
# Runs on Linux, macOS and Git Bash on Windows.
set -euo pipefail
export MSYS_NO_PATHCONV=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PHONE=${ZTOS_PHONE:-zerone@172.16.42.1}
PORT=${ZTOS_SSH_PORT:-22}
CMD=${1:-}
case "$CMD" in
save) FILE=${2:-$ROOT/backups/starqltechn/ztos-data-$(date +%Y%m%d-%H%M).tar.gz} ;;
restore) FILE=${2:?the file upgrade.sh save made} ;;
*) echo "usage: upgrade.sh save [file] | restore <file>" >&2; exit 2 ;;
esac

# What is the user's, relative to /: one path a line (globs allowed)
KEEP='home
etc/NetworkManager/system-connections
var/lib/bluetooth
etc/ztoscorenetworking
var/lib/ztoscorenetworking
var/lib/zrnperfd
var/lib/ztoscsf-sensord
var/lib/zrn-sleep
var/lib/zrn-power
var/lib/ztos-starq
var/lib/waydroid
etc/localtime
etc/ssh/ssh_host_*'

# On the phone, as root. Its stdout is the archive: everything else to stderr.
SAVE='set -eu
exec 3>&1 1>&2
. /etc/ztos/user.conf 2> /dev/null || true
u=${ZTOS_USER:-$(id -nu 1000)}
m=$(mktemp -d)
trap "rm -rf $m" EXIT
mkdir "$m/ztos-upgrade"
printf "user=%s\nuid=%s\n" "$u" "$(id -u "$u")" > "$m/ztos-upgrade/info"
getent shadow "$u" | cut -d: -f2 > "$m/ztos-upgrade/password"
pacman -Qqe > "$m/ztos-upgrade/packages" 2> /dev/null || true
# Android stops first, so that its data is copied at rest
wd=
if systemctl -q is-active waydroid-container 2> /dev/null; then
	wd=1
	systemctl stop waydroid-container
fi
cd /
set --
for p in $KEEP; do
	if [ -e "$p" ] || [ -L "$p" ]; then set -- "$@" "$p"; fi
done
echo "phone: saving $*"
# (1: a file changed while read, a log; only 2 is a failure)
r=0
tar -czf - --numeric-owner --xattrs --warning=no-file-changed \
	-C "$m" ztos-upgrade -C / "$@" >&3 || r=$?
[ -z "$wd" ] || systemctl start waydroid-container || true
[ "$r" -le 1 ]'

RESTORE='set -eu
a=$1
. /etc/ztos/user.conf 2> /dev/null || true
u=${ZTOS_USER:-$(id -nu 1000)}
m=$(mktemp -d)
# (the copy holds Wi-Fi passwords and messages: gone however this ends)
trap "rm -rf $m; rm -f $a" EXIT
[ ! -e /etc/zboot-firstboot ] || { echo "phone: the first boot has not finished: wait for the lock screen, then run restore again" >&2; exit 1; }
tar -xzf "$a" -C "$m" ztos-upgrade
su=$(sed -n "s/^user=//p" "$m/ztos-upgrade/info")
suid=$(sed -n "s/^uid=//p" "$m/ztos-upgrade/info")
if [ "$su" != "$u" ] || [ "$suid" != "$(id -u "$u")" ]; then
	echo "phone: the saved data is user $su (uid $suid), this system has $u (uid $(id -u "$u")): install with --user $su" >&2
	exit 1
fi
# Nothing may write over what comes back: the session, Android, the radios
for s in greetd waydroid-container bluetooth NetworkManager ztoscorenetworking; do
	systemctl stop "$s" 2> /dev/null || true
done
set -- --exclude=ztos-upgrade
if [ -e /var/lib/waydroid/images/system.img ]; then
	set -- "$@" --exclude=var/lib/waydroid
	echo "phone: keeping the new system'"'"'s Waydroid images" >&2
fi
tar -xzpf "$a" -C / --numeric-owner --xattrs --overwrite --warning=no-timestamp "$@"
h=$(cat "$m/ztos-upgrade/password")
case "$h" in
""|"!"*|"*"*) ;;
*) printf "%s:%s\n" "$u" "$h" | chpasswd -e ;;
esac
pacman -Qq > "$m/now" 2> /dev/null || true
grep -vxFf "$m/now" "$m/ztos-upgrade/packages" | tr "\n" " " > "$m/missing" || true
if [ -s "$m/missing" ]; then
	echo "Packages you had installed that the new version does not have:"
	echo "  sudo pacman -S --needed $(cat "$m/missing")"
fi
sync
if systemd-run -q --on-active=3 systemctl reboot 2> /dev/null; then
	echo "phone: restored; rebooting"
else
	echo "phone: restored; reboot it"
fi'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
read -rsp "Password of ${PHONE%@*} on the phone: " PW
echo
# ssh takes the password from SSH_ASKPASS, sudo from stdin: asked once
printf '#!/bin/sh\nprintf "%%s\\n" "$ZTOS_PW"\n' > "$TMP/askpass"
chmod 700 "$TMP/askpass"
export ZTOS_PW=$PW SSH_ASKPASS=$TMP/askpass SSH_ASKPASS_REQUIRE=force DISPLAY=${DISPLAY:-:0}
# The USB link has the computer at its other end only, and the phone's host
# key is new after every flash (until restore brings the old one back)
SSH=(ssh -p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
	-o NumberOfPasswordPrompts=1 -o ConnectTimeout=10 "$PHONE")
# as_root SCRIPT [ARG...]: the script goes along in the command (base64: no
# quoting), the password on stdin for sudo
as_root() {
	local b64 script=$1
	shift
	b64=$(printf 'KEEP="%s"\n%s\n' "$(printf '%s' "$KEEP" | tr '\n' ' ')" "$script" | base64 | tr -d '\n')
	printf '%s\n' "$PW" | "${SSH[@]}" "f=\$(mktemp) && echo $b64 | base64 -d > \"\$f\" && sudo -S -p '' sh \"\$f\" $*; r=\$?; rm -f \"\$f\"; exit \$r"
}

case "$CMD" in
save)
	mkdir -p "$(dirname "$FILE")"
	echo "saving the phone's data to $FILE (a few minutes with a big home or Android)"
	if ! (umask 077; as_root "$SAVE" > "$FILE.part") || ! gzip -t "$FILE.part"; then
		rm -f "$FILE.part"
		echo "saving failed: nothing was changed on the phone; run save again" >&2
		exit 1
	fi
	mv "$FILE.part" "$FILE"
	ls -l "$FILE"
	echo "saved. Now flash the new version in TWRP (flash-root.sh, flash.sh BOOT), boot it, wait for"
	echo "the lock screen and run: devices/samsung-starqltechn/scripts/upgrade.sh restore $FILE"
	;;
restore)
	[ -s "$FILE" ] && gzip -t "$FILE" || { echo "$FILE: not a file upgrade.sh save made, or damaged" >&2; exit 1; }
	R=/var/tmp/ztos-restore.tar.gz
	echo "sending $FILE"
	"${SSH[@]}" "umask 077 && cat > $R" < "$FILE"
	[ "$("${SSH[@]}" sha256sum $R | cut -d' ' -f1)" = "$(sha256sum "$FILE" | cut -d' ' -f1)" ] ||
		{ echo "the copy on the phone differs: run restore again" >&2; exit 1; }
	as_root "$RESTORE" "$R"
	;;
esac
