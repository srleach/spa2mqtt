"""Payload ciphers of the "encrypted" Balboa/Sundance/Jacuzzi boards (docs/protocol.md §3).

Status (C4): payload[0] is a per-frame random key and every other byte is XORed with it.
:func:`unkey` removes it and keeps all 33 bytes; each field then reads its own byte with a fixed
offset (protocol.md §3.3). :func:`fold` is the older pairwise reading, d[j] = p[2j] ^ p[2j+1] ^ 1,
which merges each pair of bytes into one value (protocol.md §3.2).

Commands (CC): payload = [K, K ^ 0xE0 ^ code]; any key K decodes to the same code.
"""

from __future__ import annotations

CC_XOR = 0xE0


def fold(payload: bytes) -> bytes:
    return bytes(payload[i] ^ payload[i + 1] ^ 1 for i in range(0, len(payload) - 1, 2))


def unkey(payload: bytes) -> bytes:
    """Remove the per-frame key: out[i] = payload[i] ^ payload[0]. out[0] is always 0."""
    if not payload:
        return b""
    k = payload[0]
    return bytes(b ^ k for b in payload)


def decrypt(payload: bytes, stream: bytes) -> bytes:
    """Plaintext status payload: plain[i] = payload[i] ^ payload[0] ^ stream[i] (protocol.md §3.3)."""
    u = unkey(payload)
    return bytes(b ^ s for b, s in zip(u, stream, strict=False)) + u[len(stream) :]


def rekey(unkeyed: bytes, key: int) -> bytes:
    """Inverse of :func:`unkey`. Used to synthesise test frames only."""
    return bytes([key]) + bytes(b ^ key for b in unkeyed[1:])


def unkeyed_from_fold(folded: bytes, template: bytes, byte_masks: dict[int, int]) -> bytes:
    """Rebuild a plausible unkeyed payload from a fold-decoded one (legacy logs).

    Starts from ``template`` (a real unkeyed payload of the same tub) and, pair by pair, flips the
    bits needed so that the pair folds to the logged value. Each flipped bit goes to the byte whose
    fields use it (``byte_masks``); where both or neither do, it goes to the even byte, or to byte
    1 for pair 0 (byte 0 is the key position). The result folds back to ``folded`` exactly.
    """
    out = bytearray(template)
    for j, value in enumerate(folded):
        a, b = 2 * j, 2 * j + 1
        if b >= len(out):
            break
        diff = (value ^ 1) ^ out[a] ^ out[b]
        for bit in range(8):
            m = 1 << bit
            if not diff & m:
                continue
            in_a = bool(byte_masks.get(a, 0) & m)
            in_b = bool(byte_masks.get(b, 0) & m)
            target = b if (a == 0 or (in_b and not in_a)) else a
            out[target] ^= m
    return bytes(out)


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
