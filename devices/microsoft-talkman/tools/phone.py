#!/usr/bin/env python3
"""Run a shell script on the phone's rescue telnet: phone.py [--timeout N] < script"""
import socket
import sys
import time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
MARK = "ZTOS-END-OF-OUTPUT"


def clean(sock, data):
    """Refuse every telnet option and return the plain bytes."""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b != IAC:
            out.append(b)
            i += 1
        elif i + 1 < len(data) and data[i + 1] in (DO, DONT, WILL, WONT):
            if i + 2 < len(data):
                reply = WONT if data[i + 1] == DO else DONT
                if data[i + 1] in (DO, WILL):
                    sock.sendall(bytes([IAC, reply, data[i + 2]]))
            i += 3
        elif i + 1 < len(data) and data[i + 1] == SB:
            end = data.find(bytes([IAC, SE]), i)
            i = end + 2 if end >= 0 else len(data)
        else:
            i += 2
    return bytes(out)


def main():
    limit = 60
    if len(sys.argv) > 2 and sys.argv[1] == "--timeout":
        limit = int(sys.argv[2])
    script = sys.stdin.read()
    sock = socket.create_connection(("172.16.42.1", 23), timeout=10)
    sock.settimeout(1)
    time.sleep(0.5)
    try:
        clean(sock, sock.recv(65536))
    except socket.timeout:
        pass
    sock.sendall(("stty -echo 2>/dev/null; PS1=; {\n" + script + "\n} 2>&1; echo " + MARK[:4] + "''" + MARK[4:] + "\n").encode())
    got = b""
    end = time.time() + limit
    while time.time() < end:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            break
        got += clean(sock, chunk)
        if MARK.encode() in got:
            break
    text = got.decode("utf-8", "replace").replace("\r", "")
    sys.stdout.buffer.write(text.split(MARK)[0].encode("utf-8", "replace"))
    if MARK not in text:
        sys.exit("phone.py: no end marker within the time limit")


if __name__ == "__main__":
    main()
