from __future__ import annotations

from pathlib import Path

import pytest

from spa2mqtt.captures import read_capture
from spa2mqtt.definitions import TubDefinition, load_definition
from spa2mqtt.protocol import Frame, FrameDecoder

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURES = FIXTURES / "captures"
RAW_D1 = CAPTURES / "raw" / "2025-05-16_j235_c4_frames.log"
RAW_D7 = CAPTURES / "raw" / "2026-11-04T220754Z_j235_labelled.log"
DECODED = sorted((CAPTURES / "decoded").glob("*.csv"))


def frames_of(path: Path) -> list[Frame]:
    dec = FrameDecoder()
    out: list[Frame] = []
    for rec in read_capture(path):
        if rec.kind == "RX":
            out.extend(dec.feed(rec.data))
    return out


@pytest.fixture(scope="session")
def j235() -> TubDefinition:
    return load_definition("jacuzzi_j235")


@pytest.fixture(scope="session")
def d7_frames() -> list[Frame]:
    return frames_of(RAW_D7)
