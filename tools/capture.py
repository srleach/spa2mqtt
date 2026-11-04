#!/usr/bin/env python3
"""Read-only raw capture from an RS485-to-TCP bridge (e.g. EW11A on port 8899).

SAFETY: this tool never writes to the socket. There is no send/sendall call in
this file. Typed labels are written to the log file only, never to the tub.

    python3 tools/capture.py 192.168.25.73 [8899]

While it runs, type a short label and press Enter before each topside action
(e.g. "p1 press 1"). The log format is one record per line:

    <unix-epoch> RX <hex bytes exactly as received>
    <unix-epoch> MARK <label>

Captures in this format can be dropped into tests/fixtures/captures/raw/ and are
replayed by the test-suite and by `spa2mqtt replay`.
"""

from __future__ import annotations

import select
import socket
import sys
import time


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8899
    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(None)
    name = f"spa-capture-{int(time.time())}.log"
    with open(name, "w", encoding="ascii") as out:
        print(f"Capturing {host}:{port} to {name}. Type a label + Enter to mark; Ctrl-C to stop.")
        try:
            while True:
                readable, _, _ = select.select([sock, sys.stdin], [], [])
                if sock in readable:
                    data = sock.recv(4096)
                    if not data:
                        print("connection closed by bridge")
                        break
                    out.write(f"{time.time():.3f} RX {data.hex()}\n")
                if sys.stdin in readable:
                    label = sys.stdin.readline().strip()
                    out.write(f"{time.time():.3f} MARK {label}\n")
                out.flush()
        except KeyboardInterrupt:
            pass
    print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
