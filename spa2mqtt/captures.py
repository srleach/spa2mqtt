"""Capture file formats.

* ``.log``: ``<epoch> RX <hex>`` and ``<epoch> MARK <label>`` lines (tools/capture.py).
  Text after ``#`` is a comment.
* ``.csv``: legacy decoded status payloads (16 comma-separated ints per row). These are
  re-encoded into synthetic status frames with a varying key so the whole pipeline can be
  exercised. Frames synthesised this way are test data, not wire captures.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .protocol.cipher import unfold
from .protocol.frame import Frame


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    timestamp: float
    kind: Literal["RX", "MARK"]
    data: bytes = b""
    label: str = ""


def read_capture(path: Path, status_type: int = 0xC4) -> Iterator[CaptureRecord]:
    if path.suffix == ".csv":
        yield from _read_decoded_csv(path, status_type)
        return
    with path.open(encoding="ascii") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            ts, kind, rest = [*line.split(None, 2), "", ""][:3]
            if kind == "RX":
                yield CaptureRecord(float(ts), "RX", data=bytes.fromhex(rest))
            elif kind == "MARK":
                yield CaptureRecord(float(ts), "MARK", label=rest)


def synthetic_status_frame(decoded: bytes, key: int, status_type: int = 0xC4) -> bytes:
    return Frame(addr=0xFF, mid=0xAF, type=status_type, payload=unfold(decoded, key=key)).encode()


def _read_decoded_csv(path: Path, status_type: int) -> Iterator[CaptureRecord]:
    with path.open(newline="") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if not row:
                continue
            decoded = bytes(int(v) for v in row)
            key = (i * 37 + 11) & 0xFF  # deterministic, varies per frame like the real key
            yield CaptureRecord(i * 0.3, "RX", data=synthetic_status_frame(decoded, key, status_type))
