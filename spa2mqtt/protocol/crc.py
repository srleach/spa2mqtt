"""CRC-8 used by Balboa-family boards: poly 0x07, init 0x02, no reflection, xorout 0x02.

Equivalent to the "augmented, register 0xB5" formulation in garbled1/pybalboa; see
docs/protocol.md §2 and tools/research/analyze_captures.py crc.
"""

from __future__ import annotations

POLY = 0x07
INIT = 0x02
XOR_OUT = 0x02


def _make_table() -> tuple[int, ...]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = ((crc << 1) ^ POLY) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table.append(crc)
    return tuple(table)


_TABLE = _make_table()


def crc8(data: bytes | bytearray | memoryview) -> int:
    """CRC over the frame bytes from LEN through the last payload byte."""
    crc = INIT
    for b in data:
        crc = _TABLE[crc ^ b]
    return crc ^ XOR_OUT
