#!/usr/bin/env python3
"""ztOS's two partitions in a Lumia 950's GPT, in place of Windows' MainOS and Data.

  gpt-talkman.py check <primary.bin> <backup.bin>              says what it would do
  gpt-talkman.py make  <primary.bin> <backup.bin> <outdir>     writes the new tables

primary.bin is the disk's first 34 sectors, backup.bin its last 33. MainOS becomes
"boot" (LK looks for that name, 64 MiB), and "ztos-root" takes the rest of MainOS
and all of Data. No other entry changes, and the tables stay where they are. Everything
up to and including EFIESP, the phone's identity and firmware partitions among them,
is left exactly as it was; so is MMOS.

Refuses anything that does not look like this phone's table, and checks its own
output by parsing it again.
"""
import struct
import sys
import zlib
from pathlib import Path

SECTOR = 512
BOOT_SECTORS = 64 * 1024 * 1024 // SECTOR
ALIGN = 1024 * 1024 // SECTOR
# must exist and must not move
KEEP = ("DPP", "MODEM_FS1", "MODEM_FS2", "MODEM_FSC", "MODEM_FSG", "SEC", "SSD", "UEFI", "SBL1",
        "TZ", "RPM", "HYP", "EFIESP", "IS_UNLOCKED")


def parse(primary):
    header = primary[SECTOR:2 * SECTOR]
    if header[:8] != b"EFI PART":
        sys.exit("gpt: no GPT signature in sector 1")
    size, = struct.unpack_from("<I", header, 12)
    crc, = struct.unpack_from("<I", header, 16)
    check = bytearray(header[:size])
    check[16:20] = b"\0\0\0\0"
    if zlib.crc32(bytes(check)) != crc:
        sys.exit("gpt: header CRC is wrong")
    cur, alt, first, last = struct.unpack_from("<QQQQ", header, 24)
    start, count, entry, ecrc = struct.unpack_from("<QIII", header, 72)
    table = primary[start * SECTOR:start * SECTOR + count * entry]
    if len(table) != count * entry or zlib.crc32(table) != ecrc:
        sys.exit("gpt: entries' CRC is wrong")
    entries = {}
    for i in range(count):
        e = table[i * entry:i * entry + entry]
        if e[:16] == b"\0" * 16:
            continue
        name = e[56:128].decode("utf-16-le").split("\0")[0]
        s, n = struct.unpack_from("<QQ", e, 32)
        if name in entries:
            sys.exit(f"gpt: two partitions named {name}")
        entries[name] = (i, s, n)
    return dict(size=size, cur=cur, alt=alt, first=first, last=last, start=start,
                count=count, entry=entry, table=bytearray(table), entries=entries, header=header)


def rebuild_header(g, cur, alt, table_lba, new_crc):
    h = bytearray(g["header"][:g["size"]])
    struct.pack_into("<QQ", h, 24, cur, alt)
    struct.pack_into("<Q", h, 72, table_lba)
    struct.pack_into("<I", h, 88, new_crc)
    h[16:20] = b"\0\0\0\0"
    struct.pack_into("<I", h, 16, zlib.crc32(bytes(h)))
    return bytes(h).ljust(SECTOR, b"\0")


def set_entry(g, index, name, start, end):
    off = index * g["entry"]
    e = g["table"]
    struct.pack_into("<QQ", e, off + 32, start, end)
    raw = name.encode("utf-16-le").ljust(72, b"\0")
    e[off + 56:off + 128] = raw


def plan(g):
    names = g["entries"]
    for name in KEEP + ("MainOS", "Data"):
        if name not in names:
            sys.exit(f"gpt: no {name}: this is not the table this tool expects")
    if "boot" in names or "ztos-root" in names:
        sys.exit("gpt: already has ztOS's partitions")
    _, main_s, main_e = names["MainOS"]
    _, data_s, data_e = names["Data"]
    if data_s <= main_e or data_e > g["last"]:
        sys.exit("gpt: MainOS and Data are not in the expected order")
    esp_end = names["EFIESP"][2]
    if main_s <= esp_end:
        sys.exit("gpt: MainOS does not come after EFIESP")
    for name, (_, s, e) in names.items():
        if name in ("MainOS", "Data"):
            continue
        if not (e < main_s or s > data_e):
            sys.exit(f"gpt: {name} sits inside the range to be replaced")
    boot_end = main_s + BOOT_SECTORS - 1
    root_start = (boot_end + ALIGN) // ALIGN * ALIGN
    return main_s, boot_end, root_start, data_e


def main():
    mode, primary_path, backup_path = sys.argv[1:4]
    primary = Path(primary_path).read_bytes()
    backup = Path(backup_path).read_bytes()
    if len(primary) != 34 * SECTOR or len(backup) != 33 * SECTOR:
        sys.exit("gpt: primary is 34 sectors, backup 33")
    g = parse(primary)
    boot_s, boot_e, root_s, root_e = plan(g)
    names = g["entries"]
    print(f"entries {len(names)}; disk last usable LBA {g['last']}, backup header LBA {g['alt']}")
    print(f"boot      LBA {boot_s}-{boot_e} ({(boot_e - boot_s + 1) * SECTOR // 1048576} MiB)")
    print(f"ztos-root LBA {root_s}-{root_e} ({(root_e - root_s + 1) * SECTOR // 1048576} MiB)")
    if mode == "check":
        return

    before = {k: v for k, v in names.items() if k not in ("MainOS", "Data")}
    set_entry(g, names["MainOS"][0], "boot", boot_s, boot_e)
    set_entry(g, names["Data"][0], "ztos-root", root_s, root_e)
    table = bytes(g["table"])
    crc = zlib.crc32(table)

    new_primary = bytearray(primary)
    new_primary[SECTOR:2 * SECTOR] = rebuild_header(g, g["cur"], g["alt"], g["start"], crc)
    new_primary[g["start"] * SECTOR:g["start"] * SECTOR + len(table)] = table

    # the backup: its entries, then its header in the disk's last sector
    backup_table_lba = g["alt"] - len(table) // SECTOR
    new_backup = bytearray(backup)
    new_backup[:len(table)] = table
    new_backup[len(table):len(table) + SECTOR] = rebuild_header(g, g["alt"], g["cur"], backup_table_lba, crc)

    again = parse(bytes(new_primary))
    assert again["entries"]["boot"][1:] == (boot_s, boot_e)
    assert again["entries"]["ztos-root"][1:] == (root_s, root_e)
    for name, value in before.items():
        assert again["entries"][name] == value, name
    assert len(again["entries"]) == len(names)

    out = Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    (out / "primary.new").write_bytes(new_primary)
    (out / "backup.new").write_bytes(new_backup)
    print(f"written and parsed again, {len(before)} other entries unchanged; backup table at LBA {backup_table_lba}")


if __name__ == "__main__":
    main()
