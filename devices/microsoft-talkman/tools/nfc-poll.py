#!/usr/bin/env python3
"""Turn NFC on and look for a tag, to see that the chip works. Run as root on the phone:

    python3 nfc-poll.py [seconds]

Prints the kind of tag it finds, never the tag's own ID. Nothing is read from or written to the tag.
The kernel's NFC interface is enough for this: neard, the usual tool, is not in the package repositories.
"""
import os
import select
import socket
import struct
import sys
import time

NETLINK_GENERIC, SOL_NETLINK, ADD_MEMBERSHIP = 16, 270, 1
NLM_F_REQUEST, NLM_F_ACK = 1, 4
NLMSG_ERROR, GENL_ID_CTRL = 2, 16
CMD_GETFAMILY, CTRL_ATTR_NAME, CTRL_ATTR_ID, CTRL_ATTR_GROUPS = 3, 2, 1, 7
DEV_UP, DEV_DOWN, START_POLL, STOP_POLL, GET_TARGET, TARGETS_FOUND = 2, 3, 6, 7, 8, 9
ATTR_DEVICE, ATTR_PROTOCOLS, ATTR_IM_PROTOCOLS = 1, 3, 13
PROTOCOLS = {1: 'Jewel', 2: 'MIFARE', 3: 'FeliCa', 4: 'ISO 14443 A', 5: 'NFC-DEP (a phone)', 6: 'ISO 14443 B', 7: 'ISO 15693'}
ALL = sum(1 << n for n in PROTOCOLS)


def attr(kind, data):
    size = 4 + len(data)
    return struct.pack('<HH', size, kind) + data + b'\0' * (-size % 4)


def attrs(data):
    out = {}
    while len(data) >= 4:
        size, kind = struct.unpack_from('<HH', data)
        if size < 4:
            break
        out[kind & 0x3fff] = data[4:size]
        data = data[(size + 3) & ~3:]
    return out


class Netlink:
    def __init__(self):
        self.sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_GENERIC)
        self.sock.bind((0, 0))
        self.seq = 0

    def send(self, family, cmd, payload=b''):
        self.seq += 1
        size = 16 + 4 + len(payload)
        self.sock.send(struct.pack('<IHHII', size, family, NLM_F_REQUEST | NLM_F_ACK, self.seq, 0) +
                       struct.pack('<BBH', cmd, 1, 0) + payload)

    def messages(self, timeout):
        if not select.select([self.sock], [], [], timeout)[0]:
            return
        data = self.sock.recv(65536)
        while len(data) >= 16:
            size, kind, _, seq, _ = struct.unpack_from('<IHHII', data)
            yield kind, seq, data[16:size]
            data = data[(size + 3) & ~3:]

    def call(self, family, cmd, payload=b''):
        """Returns (error, reply's attributes)."""
        self.send(family, cmd, payload)
        reply = {}
        end = time.time() + 5
        while time.time() < end:
            for kind, seq, body in self.messages(0.5):
                if seq != self.seq:
                    continue
                if kind == NLMSG_ERROR:
                    return -struct.unpack_from('<i', body)[0], reply
                reply = attrs(body[4:])
        return 110, reply


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30
    nl = Netlink()
    err, family = nl.call(GENL_ID_CTRL, CMD_GETFAMILY, attr(CTRL_ATTR_NAME, b'nfc\0'))
    if err:
        sys.exit('no NFC in this kernel: %s' % os.strerror(err))
    nfc = struct.unpack('<H', family[CTRL_ATTR_ID])[0]
    for group in attrs(family[CTRL_ATTR_GROUPS]).values():
        g = attrs(group)
        if g.get(1, b'').rstrip(b'\0') == b'events':
            nl.sock.setsockopt(SOL_NETLINK, ADD_MEMBERSHIP, struct.unpack('<I', g[2])[0])
    device = attr(ATTR_DEVICE, struct.pack('<I', 0))
    err, _ = nl.call(nfc, DEV_UP, device)
    print('chip on:', os.strerror(err) if err else 'yes')
    if err and err != 114:      # 114: it already was
        sys.exit(1)
    try:
        err, _ = nl.call(nfc, START_POLL, device + attr(ATTR_IM_PROTOCOLS, struct.pack('<I', ALL)))
        print('polling:', os.strerror(err) if err else 'yes, hold a tag or card to the back of the phone')
        if err:
            sys.exit(1)
        found = 0
        end = time.time() + seconds
        while time.time() < end and not found:
            for _, _, body in nl.messages(0.5):
                if len(body) >= 4 and body[0] == TARGETS_FOUND:
                    found += 1
        if not found:
            print('no tag in %d s' % seconds)
            return
        nl.seq += 1
        size = 16 + 4 + len(device)
        nl.sock.send(struct.pack('<IHHII', size, nfc, NLM_F_REQUEST | 0x300, nl.seq, 0) +
                     struct.pack('<BBH', GET_TARGET, 1, 0) + device)
        end = time.time() + 3
        while time.time() < end:
            for kind, seq, body in nl.messages(0.5):
                if seq == nl.seq and kind == nfc:
                    bits = struct.unpack('<I', attrs(body[4:]).get(ATTR_PROTOCOLS, b'\0\0\0\0'))[0]
                    print('FOUND a tag:', ', '.join(n for b, n in PROTOCOLS.items() if bits >> b & 1) or hex(bits))
                    return
                if seq == nl.seq and kind in (2, 3):
                    print('FOUND a tag, of a kind not reported')
                    return
    finally:
        nl.call(nfc, STOP_POLL, device)
        nl.call(nfc, DEV_DOWN, device)


if __name__ == '__main__':
    main()
