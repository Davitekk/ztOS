#!/usr/bin/env python3
"""Install ztOS on the Lumia 950 from its rescue shell: new partitions, root, boot image.

  install-talkman.py --root root.img --boot boot.img --backup BACKUP_FOLDER

The phone must be running the rescue image from RAM (fastboot boot). Stops at the first
thing that does not match. Writes only: the GPT's two copies, then the ztos-root partition;
the boot image goes in through LK's fastboot. The old tables are saved in the backup folder.
"""
import argparse
import hashlib
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
GPT = TOOLS / "gpt-talkman.py"
PHONE = TOOLS / "phone.py"
ROOT_IMG = BOOT_IMG = BACKUP = ROOT_SHA = None
DISK = "/dev/mmcblk1"
SECTORS = 61071360
BACKUP_LBA = 61071327
WORK = Path("build/install")
HOST = "172.16.42.1"


def say(*words):
    print(*words, flush=True)


def phone(script, timeout=60):
    r = subprocess.run([sys.executable, str(PHONE), "--timeout", str(timeout)],
                       input=script + "\n", capture_output=True, text=True, errors="replace")
    if r.returncode:
        sys.exit(f"phone: {r.stderr.strip()}")
    # the shell echoes the script until stty takes effect: keep what follows the echo
    text = r.stdout.split("ZTOS''-END-OF-OUTPUT", 1)
    return (text[1] if len(text) > 1 else r.stdout).strip()


def pull(cmd, path):
    phone(f"({cmd} 2>/dev/null | nc -l -p 5001) >/dev/null 2>&1 &")
    time.sleep(0.7)
    with socket.create_connection((HOST, 5001), timeout=20) as s, open(path, "wb") as f:
        s.settimeout(30)
        while True:
            b = s.recv(1 << 20)
            if not b:
                break
            f.write(b)


def push(path, remote):
    phone(f"(nc -l -p 5002 > {remote}) >/dev/null 2>&1 &")
    time.sleep(0.7)
    with socket.create_connection((HOST, 5002), timeout=20) as s:
        s.sendall(Path(path).read_bytes())
        s.shutdown(socket.SHUT_WR)
    time.sleep(1)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def phone_sha(cmd, timeout=60):
    out = phone(f"{cmd} 2>/dev/null | sha256sum", timeout)
    m = re.search(r"\b[0-9a-f]{64}\b", out)
    if not m:
        sys.exit(f"no hash from the phone: {out!r}")
    return m.group(0)


def partition(name):
    out = phone("for u in /sys/class/block/mmcblk1p*/uevent; do "
                f"grep -qx PARTNAME={name} $u && echo FOUND ${{u%/uevent}} "
                "$(cat ${u%uevent}start) $(cat ${u%uevent}size); done")
    m = re.findall(r"FOUND (/sys/class/block/(\S+)) (\d+) (\d+)", out)
    if len(m) != 1:
        return None
    return m[0][1], int(m[0][2]), int(m[0][3])


def write_gpt():
    WORK.mkdir(parents=True, exist_ok=True)
    pull(f"dd if={DISK} bs=512 count=34", WORK / "primary.bin")
    pull(f"dd if={DISK} bs=512 skip={BACKUP_LBA} count=33", WORK / "backup.bin")
    # the rollback: the table as it was today, beside the full backup
    BACKUP.mkdir(parents=True, exist_ok=True)
    (BACKUP / "gpt-before-ztos-primary.bin").write_bytes((WORK / "primary.bin").read_bytes())
    (BACKUP / "gpt-before-ztos-backup.bin").write_bytes((WORK / "backup.bin").read_bytes())
    r = subprocess.run([sys.executable, str(GPT), "make", str(WORK / "primary.bin"), str(WORK / "backup.bin"),
                        str(WORK / "new")], capture_output=True, text=True)
    say(r.stdout.strip())
    if r.returncode:
        sys.exit(f"gpt: {r.stderr.strip()}")
    for name, lba, count in (("primary", 0, 34), ("backup", BACKUP_LBA, 33)):
        local = WORK / "new" / f"{name}.new"
        push(local, f"/tmp/{name}.new")
        if phone_sha(f"cat /tmp/{name}.new") != sha(local):
            sys.exit(f"{name}: the copy on the phone differs")
        phone(f"dd if=/tmp/{name}.new of={DISK} bs=512 seek={lba} count={count} conv=fsync 2>&1; sync")
        if phone_sha(f"dd if={DISK} bs=512 skip={lba} count={count}") != sha(local):
            sys.exit(f"{name}: the table on the disk differs from what was written")
        say(f"{name} table written and read back")
    say(phone(f"blockdev --rereadpt {DISK} 2>&1 && echo reread ok")[:80])
    time.sleep(2)


def write_root():
    part = partition("ztos-root")
    if not part:
        sys.exit("no partition named ztos-root")
    dev, start, size = part
    say(f"ztos-root is {dev}, LBA {start}, {size} sectors")
    if start != 475136 or size != 60596191:
        sys.exit("ztos-root is not where the new table puts it")
    length = ROOT_IMG.stat().st_size
    if length % (4 << 20) or length > size * 512:
        sys.exit("the root image does not fit")
    phone(f"(nc -l -p 5003 | dd of=/dev/{dev} bs=4M conv=fsync > /tmp/dd.log 2>&1; echo done >> /tmp/dd.log) >/dev/null 2>&1 &")
    time.sleep(1)
    sent = 0
    started = time.time()
    with socket.create_connection((HOST, 5003), timeout=30) as s, open(ROOT_IMG, "rb") as f:
        s.settimeout(120)
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            s.sendall(chunk)
            sent += len(chunk)
            if sent % (512 << 20) == 0:
                rate = sent / (time.time() - started) / 1e6
                say(f"  {sent >> 20} of {length >> 20} MiB, {rate:.0f} MB/s")
        s.shutdown(socket.SHUT_WR)
    for _ in range(300):
        if "done" in phone("cat /tmp/dd.log"):
            break
        time.sleep(2)
    else:
        sys.exit("dd did not finish")
    say(phone("cat /tmp/dd.log; sync")[:200])
    say("checking what is on the partition (a few minutes)")
    got = phone_sha(f"dd if=/dev/{dev} bs=4M count={length >> 22}", 900)
    if got != ROOT_SHA:
        sys.exit(f"the root on the phone differs: {got}")
    say("root written and read back: checksum matches")


def main():
    global ROOT_IMG, BOOT_IMG, BACKUP, ROOT_SHA
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="root.img, from the build")
    ap.add_argument("--boot", type=Path, required=True, help="ztos-talkman-boot.img, from the build")
    ap.add_argument("--backup", type=Path, required=True, help="where the old partition tables go")
    args = ap.parse_args()
    ROOT_IMG, BOOT_IMG, BACKUP = args.root, args.boot, args.backup
    say("checksumming the root image")
    ROOT_SHA = sha(ROOT_IMG)
    if int(phone("cat /sys/class/block/mmcblk1/size").split()[-1]) != SECTORS:
        sys.exit("the disk is not this phone's")
    if partition("ztos-root"):
        say("the new partitions are already there")
    else:
        if not partition("MainOS") or not partition("Data"):
            sys.exit("neither Windows' nor ztOS's partitions")
        write_gpt()
        if not partition("ztos-root"):
            sys.exit("the kernel does not see the new table yet: restart into rescue and run this again")
    write_root()
    say("rebooting into LK for the boot image")
    phone("(sleep 1; reboot -f) &")
    time.sleep(3)
    for _ in range(90):
        if subprocess.run(["fastboot", "devices"], capture_output=True, text=True).stdout.strip():
            break
        time.sleep(2)
    else:
        sys.exit("no fastboot")
    r = subprocess.run(["fastboot", "flash", "boot", str(BOOT_IMG)], capture_output=True, text=True)
    say(r.stderr.strip()[-300:])
    if r.returncode:
        sys.exit("fastboot flash boot failed")
    r = subprocess.run(["fastboot", "reboot"], capture_output=True, text=True)
    say(r.stderr.strip()[-120:])
    say("INSTALLED")


if __name__ == "__main__":
    main()
