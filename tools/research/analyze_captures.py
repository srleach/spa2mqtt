#!/usr/bin/env python3
"""Reproduce every dump-derived claim in docs/protocol.md.

Read-only: this script only reads files under tests/fixtures/captures/.
It never opens a network connection or serial port.

    python3 tools/research/analyze_captures.py            # all sections
    python3 tools/research/analyze_captures.py crc        # one section

Sections:
    crc       CRC-8 check of every raw frame; equivalence of the two CRC formulations
    cipher    pairwise-fold decode vs. key-stream decrypt, and the identity between them
    clock     hour/minute/day/month/day-of-week vs. capture wall-clock (decoded CSVs)
    profile   per-byte value histogram for each decoded CSV
    timeline  change-point timeline for each decoded CSV
    census    frame counts by (addr, mid, type) for each raw capture
    labelled  raw captures with MARK lines: C4/CA changes and panel button codes, interleaved
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURES = ROOT / "tests" / "fixtures" / "captures"


# --- CRC ---------------------------------------------------------------------


def crc8_augmented(data: bytes) -> int:
    """garbled1 / Balboa formulation: register 0xB5, augmented, final ^0x02."""
    crc = 0xB5
    for cur in data:
        for i in range(8):
            bit = crc & 0x80
            crc = ((crc << 1) & 0xFF) | ((cur >> (7 - i)) & 0x01)
            if bit:
                crc ^= 0x07
    for _ in range(8):
        bit = crc & 0x80
        crc = (crc << 1) & 0xFF
        if bit:
            crc ^= 0x07
    return crc ^ 0x02


def crc8_standard(data: bytes) -> int:
    """Textbook CRC-8: poly 0x07, init 0x02, no reflection, xorout 0x02."""
    crc = 0x02
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0x02


# --- loading -----------------------------------------------------------------


def raw_frames(path: Path) -> list[tuple[str, bytes]]:
    """Parse '<epoch> RX <hex>' capture logs into whole 0x7E..0x7E frames."""
    stream = bytearray()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "RX":
            stream += bytes.fromhex(parts[2])
    frames: list[tuple[str, bytes]] = []
    i = 0
    while i < len(stream) - 1:
        if stream[i] == 0x7E and stream[i + 1] != 0x7E:
            n = stream[i + 1]
            end = i + n + 1
            if end < len(stream) and stream[end] == 0x7E:
                frames.append((f"{path.name}@{i}", bytes(stream[i : end + 1])))
                i = end + 1
                continue
        i += 1
    return frames


def decoded_csvs() -> list[Path]:
    return sorted((CAPTURES / "decoded").glob("*.csv"))


def load_csv(path: Path) -> list[list[int]]:
    with path.open(newline="") as f:
        return [list(map(int, r)) for r in csv.reader(f) if r]


def fold(body: bytes) -> bytes:
    """Pairwise fold (HyperActiveJ xormsg): d[j] = b[2j] ^ b[2j+1] ^ 1."""
    return bytes(body[j] ^ body[j + 1] ^ 1 for j in range(0, len(body) - 1, 2))


TYPE_KEY = {0xC4: 0x19, 0xCA: 0x59, 0xCC: 0xDF}


def keystream_decrypt(frame: bytes) -> bytes:
    """pyjacuzzi decrypt(): key1 = f[5]^c(type); key2 counts down mod 64."""
    p = bytearray(frame)
    length = p[1]
    key1 = p[5] ^ TYPE_KEY[p[4]]
    key2 = length - 7
    for i in range(6, length):
        key2 = (key2 - 1) % 64
        p[i] ^= key1 ^ key2
    return bytes(p)


# --- sections ----------------------------------------------------------------


def section_crc() -> None:
    print("== crc: every raw frame, both formulations")
    for log in sorted((CAPTURES / "raw").glob("*.log")):
        frames = raw_frames(log)
        ok = sum(crc8_augmented(f[1:-2]) == f[-2] for _, f in frames)
        same = all(crc8_augmented(f[1:-2]) == crc8_standard(f[1:-2]) for _, f in frames)
        len_ok = all(f[1] == len(f) - 2 for _, f in frames)
        print(f"  {log.name}: {len(frames)} frames, crc ok {ok}/{len(frames)}, "
              f"formulations agree={same}, LEN==len(frame)-2: {len_ok}")


def section_cipher() -> None:
    print("== cipher: fold vs key-stream decrypt on raw C4 frames")
    for log in sorted((CAPTURES / "raw").glob("*.log")):
        frames = [f for _, f in raw_frames(log) if f[4] == 0xC4]
        distinct: Counter[str] = Counter()
        identity_holds = True
        for f in frames:
            body = f[5:-2]
            d = fold(body)
            p = keystream_decrypt(f)
            # identity: d[0] == p[6]^0x06 ; d[k] == p[5+2k]^p[6+2k] for k>=1
            if d[0] != p[6] ^ 0x06:
                identity_holds = False
            for k in range(1, 16):
                if d[k] != p[5 + 2 * k] ^ p[6 + 2 * k]:
                    identity_holds = False
            distinct[d.hex(" ")] += 1
            # the key byte is per-frame; body XOR key is constant per state
        print(f"  {log.name}: {len(frames)} C4 frames; fold==keystream identity holds: {identity_holds}")
        keys = Counter(f[5] for f in frames)
        print(f"  distinct key bytes f[5]: {len(keys)} of {len(frames)} frames")
        for k, n in distinct.items():
            print(f"  folded x{n}: {k}")
        if frames:
            p = keystream_decrypt(frames[0])
            print(f"  key-stream plaintext P[6..37] of first frame: {p[6:38].hex(' ')}")


def _epoch_from_name(name: str) -> float | None:
    m = re.search(r"epoch(\d+)", name)
    return float(m.group(1)) if m else None


def section_clock() -> None:
    print("== clock: decoded fields vs capture wall clock (UTC). Tub is not DST-adjusted.")
    for path in decoded_csvs():
        rows = load_csv(path)
        first = rows[0]
        hour, minute = first[0] ^ 6, first[11]
        day, month, dow, year = first[7] >> 3, first[7] & 7, first[2] & 7, first[9]
        epoch = _epoch_from_name(path.name)
        wall = (dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d %a %H:%M:%S UTC")
                if epoch else "(no timestamp in name)")
        print(f"  {path.name}: tub {hour:02d}:{minute:02d} day={day} month={month} "
              f"dow(b2&7)={dow} year(b9)={year}  | file wall-clock {wall}")


def section_profile() -> None:
    print("== profile: per decoded byte, value counts and transition counts")
    for path in decoded_csvs():
        rows = load_csv(path)
        print(f"  -- {path.name}: {len(rows)} rows")
        for i in range(16):
            s = [r[i] for r in rows]
            c = Counter(s)
            tr = sum(a != b for a, b in zip(s, s[1:]))
            vals = ", ".join(f"{v}(0x{v:02X})x{n}" for v, n in sorted(c.items())[:12])
            print(f"   b{i:<2d} transitions={tr:<4d} {vals}")


def section_timeline() -> None:
    print("== timeline: runs of identical frames (ignoring minute byte 11)")
    for path in decoded_csvs():
        rows = load_csv(path)
        print(f"  -- {path.name}")
        prev = None
        start = 0
        for i, r in enumerate([*rows, None]):
            key = None if r is None else tuple(v for j, v in enumerate(r) if j != 11)
            if key != prev:
                if prev is not None:
                    x = rows[start]
                    print(f"   rows {start + 1:5d}-{i:5d} tub {x[0] ^ 6:02d}:{x[11]:02d} "
                          f"b1={x[1]:08b} b2={x[2]:08b} b3={x[3]:3d} b5={x[5]:3d}(^2/2={(x[5] ^ 2) / 2}) "
                          f"b8={x[8]} b10={x[10]:08b} b13={x[13]:3d} b14={x[14]:3d} b15={x[15]}")
                prev, start = key, i


def _frames_with_time(path: Path) -> list[tuple[float, str, bytes]]:
    """(timestamp, kind, data) where kind is 'MARK' (data=label) or 'FRAME' (data=raw frame)."""
    out: list[tuple[float, str, bytes]] = []
    buf = bytearray()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        ts = float(parts[0])
        if parts[1] == "MARK":
            out.append((ts, "MARK", parts[2].encode()))
            continue
        buf += bytes.fromhex(parts[2])
        i = 0
        while i < len(buf) - 1:
            if buf[i] == 0x7E and buf[i + 1] != 0x7E:
                end = i + buf[i + 1] + 1
                if end >= len(buf):
                    break
                if buf[end] == 0x7E and crc8_standard(bytes(buf[i + 1 : end - 1])) == buf[end - 1]:
                    out.append((ts, "FRAME", bytes(buf[i : end + 1])))
                    i = end
                    continue
            i += 1
        del buf[:i]
    return out


def section_census() -> None:
    print("== census: frames by (addr, mid, type)")
    for log in sorted((CAPTURES / "raw").glob("*.log")):
        c: Counter[tuple[int, int, int]] = Counter()
        frames = [d for _, k, d in _frames_with_time(log) if k == "FRAME"]
        for f in frames:
            c[(f[2], f[3], f[4])] += 1
        print(f"  {log.name}: {len(frames)} frames")
        for (a, m, t), n in sorted(c.items()):
            print(f"    addr=0x{a:02X} mid=0x{m:02X} type=0x{t:02X}: {n}")


def section_labelled() -> None:
    print("== labelled: changes only; CC lines show decoded button code payload[0]^payload[1]^0xE0")
    for log in sorted((CAPTURES / "raw").glob("*.log")):
        records = _frames_with_time(log)
        if not any(k == "MARK" for _, k, _ in records):
            continue
        print(f"  -- {log.name}")
        t0 = records[0][0]
        last: dict[int, bytes] = {}
        last_code = 0
        for ts, kind, data in records:
            t = ts - t0
            if kind == "MARK":
                print(f"   {t:7.1f}  MARK {data.decode()}")
                continue
            typ, body = data[4], data[5:-2]
            if typ in (0xC4, 0xCA):
                d = fold(body)
                prev = last.get(typ)
                if d != prev:
                    tag = "d" if typ == 0xC4 else "c"
                    diff = "" if prev is None else " ".join(
                        f"{tag}{i}:{prev[i]:02x}->{d[i]:02x}" for i in range(len(d)) if d[i] != prev[i])
                    print(f"   {t:7.1f}  {typ:02X} {d.hex(' ')}  {diff}")
                    last[typ] = d
            elif typ == 0xCC:
                code = body[0] ^ body[1] ^ 0xE0
                if code != last_code:
                    print(f"   {t:7.1f}  CC ch=0x{data[2]:02X} code=0x{code:02X}")
                    last_code = code


SECTIONS = {
    "crc": section_crc,
    "cipher": section_cipher,
    "clock": section_clock,
    "profile": section_profile,
    "timeline": section_timeline,
    "census": section_census,
    "labelled": section_labelled,
}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SECTIONS)
    for name in wanted:
        SECTIONS[name]()
        print()
