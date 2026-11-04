"""CRC, framing and cipher (docs/protocol.md §2-3)."""

from __future__ import annotations

import pytest

from spa2mqtt.protocol import Frame, FrameDecoder, cc_decode, cc_encode, crc8, fold, unfold

from .conftest import RAW_D1, frames_of

SC_IDLE_CC = bytes.fromhex("7E0710BFCC6585A67E")  # SpaControl sundanceRS485.py L238


def augmented_crc(data: bytes) -> int:
    """garbled1 formulation used by the legacy code."""
    crc = 0xB5
    for cur in data:
        for i in range(8):
            bit = crc & 0x80
            crc = ((crc << 1) & 0xFF) | ((cur >> (7 - i)) & 1)
            if bit:
                crc ^= 0x07
    for _ in range(8):
        bit = crc & 0x80
        crc = (crc << 1) & 0xFF
        if bit:
            crc ^= 0x07
    return crc ^ 0x02


@pytest.mark.parametrize("data", [b"", b"\x00", bytes(range(40)), b"\x7e" * 7, bytes([0xFF] * 33)])
def test_crc_matches_legacy_formulation(data: bytes) -> None:
    assert crc8(data) == augmented_crc(data)


def test_frame_roundtrip_and_known_frame() -> None:
    f = Frame(0x10, 0xBF, 0xCC, bytes([0x65, 0x85]))
    assert f.encode() == SC_IDLE_CC
    assert FrameDecoder().feed(SC_IDLE_CC) == [f]


def test_all_raw_d1_frames_decode() -> None:
    frames = frames_of(RAW_D1)
    assert len(frames) == 54
    assert {(f.addr, f.mid, f.type, len(f.payload)) for f in frames} == {(0xFF, 0xAF, 0xC4, 33)}


def test_decoder_handles_split_chunks_and_junk() -> None:
    frame = Frame(0xFF, 0xAF, 0xC4, unfold(bytes(range(16)), key=0x7E)).encode()  # key 0x7E: flags in payload
    stream = b"\x00\x13garbage\x7e" + frame + frame
    dec = FrameDecoder()
    out = []
    for i in range(0, len(stream), 3):
        out += dec.feed(stream[i : i + 3])
    assert len(out) == 2
    assert all(fold(f.payload) == bytes(range(16)) for f in out)
    assert dec.stats.bytes_dropped > 0


def test_decoder_rejects_bad_crc_and_resyncs() -> None:
    good = Frame(0x10, 0xBF, 0x06).encode()
    bad = bytearray(good)
    bad[-2] ^= 0xFF
    dec = FrameDecoder()
    assert dec.feed(bytes(bad) + good) == [Frame(0x10, 0xBF, 0x06)]
    assert dec.stats.crc_errors == 1


def test_decoder_shared_flag_between_frames() -> None:
    a = Frame(0x10, 0xBF, 0x06).encode()
    b = Frame(0xFE, 0xBF, 0x00).encode()
    assert len(FrameDecoder().feed(a + b[1:])) == 2  # "...7E" + "LEN ... 7E": one flag shared


def test_decoder_rejects_oversize_length() -> None:
    dec = FrameDecoder()
    assert dec.feed(bytes([0x7E, 0x70]) + bytes(200)) == []
    assert dec.stats.resyncs >= 1


def test_fold_is_key_independent() -> None:
    decoded = bytes.fromhex("0d000585054e20854c190026b14d2100")
    for key in (0, 0x7E, 0xFF, 0x5A):
        assert fold(unfold(decoded, key)) == decoded


def test_cc_codec() -> None:
    assert cc_decode(SC_IDLE_CC[5:7]) == 0x00
    for code in (0x01, 0x02, 0x04, 0x05, 0x12):
        for key in (0, 0x9F, 0xFF):
            assert cc_decode(cc_encode(code, key)) == code
    assert cc_encode(0x01) == bytes([0x00, 0xE1])  # == HyperActiveJ's 225 with key 0xE1/0x00
    assert cc_decode(b"\x01") is None
