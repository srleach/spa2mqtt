from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from spa2mqtt.captures import read_capture
from spa2mqtt.definitions import TubDefinition, load_definition
from spa2mqtt.protocol import Frame, FrameDecoder

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURES = FIXTURES / "captures"
RAW_D1 = CAPTURES / "raw" / "2025-05-16_j235_c4_frames.log"
RAW_D7 = CAPTURES / "raw" / "2026-11-04T220754Z_j235_labelled.log"
RAW_D8 = CAPTURES / "raw" / "2026-11-09T205918Z_j235_menu_values.log"
DECODED = sorted((CAPTURES / "decoded").glob("*.csv"))
# The J345 (plain protocol) captures, keyed as definitions/jacuzzi_j345.yaml cites them.
PLAIN = CAPTURES / "unencrypted"
PLAIN_CAPTURES = {
    "S": PLAIN / "2025-05-21_pyjacuzzi_prolink_session.txt",
    "D": PLAIN / "2025-05-21_spa2mqtt_debug_0x16.txt",
    "X1": PLAIN / "2025-05-20T1551Z_spa2mqtt_debug_idle.txt",
    "X2": PLAIN / "2025-05-20T2207Z_spa2mqtt_debug_lights.txt",
    "X3": PLAIN / "2025-05-28T0044Z_spa2mqtt_debug_panel.txt",
}
PlainLine = tuple[int, str, Frame, bytes, float]
_PLAIN_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[.,]\d+)(?::INFO:(Sending|New msg)|_): ([0-9a-f]+)$")


def frames_of(path: Path) -> list[Frame]:
    dec = FrameDecoder()
    out: list[Frame] = []
    for rec in read_capture(path):
        if rec.kind == "RX":
            out.extend(dec.feed(rec.data))
    return out


def plain_lines(path: Path) -> list[PlainLine]:
    """(line number, TX|RX, frame, raw bytes, timestamp) for the two legacy plain log shapes:
    pyjacuzzi ``<time>:INFO:Sending: <hex>`` / ``New msg: <hex>`` and spa2mqtt v1 ``<time>_: <hex>``.
    Each hex string must be exactly one frame with a good CRC."""
    out: list[PlainLine] = []
    for no, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        m = _PLAIN_LINE.match(line)
        if not m:
            continue
        raw = bytes.fromhex(m.group(3))
        dec = FrameDecoder()
        frames = dec.feed(raw)
        assert len(frames) == 1 and dec.stats.crc_errors == 0 and dec.stats.bytes_dropped == 0, (path.name, no)
        stamp = dt.datetime.fromisoformat(m.group(1).replace(",", ".")).replace(tzinfo=dt.UTC).timestamp()
        out.append((no, "TX" if m.group(2) == "Sending" else "RX", frames[0], raw, stamp))
    return out


@pytest.fixture(scope="session")
def j345() -> TubDefinition:
    return load_definition("jacuzzi_j345")


@pytest.fixture(scope="session")
def j235() -> TubDefinition:
    return load_definition("jacuzzi_j235")


@pytest.fixture(scope="session")
def d7_frames() -> list[Frame]:
    return frames_of(RAW_D7)
