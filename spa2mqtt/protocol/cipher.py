"""Payload ciphers of the "encrypted" Balboa/Sundance/Jacuzzi boards (docs/protocol.md §3).

Status (C4): pairwise fold, d[j] = p[2j] ^ p[2j+1] ^ 1. Key-independent; the 33rd payload
byte is unused. Equivalent to pyjacuzzi's key-stream decrypt (proof in protocol.md §3.2).

Commands (CC): payload = [K, K ^ 0xE0 ^ code]; any key K decodes to the same code.
"""

from __future__ import annotations

CC_XOR = 0xE0


def fold(payload: bytes) -> bytes:
    return bytes(payload[i] ^ payload[i + 1] ^ 1 for i in range(0, len(payload) - 1, 2))


def unfold(decoded: bytes, key: int = 0x00, trailing: bool = True) -> bytes:
    """Inverse of :func:`fold` for a chosen key. Used to synthesise test frames only."""
    out = bytearray()
    for value in decoded:
        out += bytes([key, key ^ value ^ 1])
    if trailing:
        out.append(key)
    return bytes(out)


def cc_encode(code: int, key: int = 0x00) -> bytes:
    if not 0 <= code <= 0xFF or not 0 <= key <= 0xFF:
        raise ValueError("code and key must be bytes")
    return bytes([key, key ^ CC_XOR ^ code])


def cc_decode(payload: bytes) -> int | None:
    if len(payload) < 2:
        return None
    return payload[0] ^ payload[1] ^ CC_XOR
