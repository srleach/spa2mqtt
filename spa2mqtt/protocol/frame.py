"""A single bus frame: 7E | LEN | ADDR | MID | TYPE | payload | CRC | 7E."""

from __future__ import annotations

from dataclasses import dataclass

from .crc import crc8

FLAG = 0x7E
HEADER_LEN = 3  # ADDR, MID, TYPE
MIN_LEN = 5  # LEN byte value: LEN + ADDR + MID + TYPE + CRC, empty payload
MAX_LEN = 64


@dataclass(frozen=True, slots=True)
class Frame:
    addr: int
    mid: int
    type: int
    payload: bytes = b""

    def encode(self) -> bytes:
        """Serialise to wire bytes, computing LEN and CRC."""
        length = len(self.payload) + MIN_LEN
        if length > MAX_LEN:
            raise ValueError(f"payload too long ({len(self.payload)} bytes)")
        body = bytes([length, self.addr, self.mid, self.type]) + self.payload
        return bytes([FLAG]) + body + bytes([crc8(body), FLAG])

    def __str__(self) -> str:
        return (
            f"Frame(addr=0x{self.addr:02X} mid=0x{self.mid:02X} type=0x{self.type:02X} "
            f"payload={self.payload.hex(' ') or '-'})"
        )
