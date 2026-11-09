"""Capture file formats.

* ``.log``: ``<epoch> RX <hex>`` and ``<epoch> MARK <label>`` lines (tools/capture.py).
  Text after ``#`` is a comment. Any other line is skipped, so a container log copied from
  ``spa2mqtt monitor --record -`` (capture lines mixed with the monitor's reports) reads too.
* ``.csv``: legacy decoded status payloads (16 comma-separated ints per row, fold-decoded).
  These are re-encoded into synthetic status frames with a varying key so the whole pipeline can
  be exercised. With a per-byte (``unkey``) definition the frames are rebuilt from the
  definition's ``fold_template`` (:func:`spa2mqtt.protocol.cipher.unkeyed_from_fold`). Frames
  synthesised this way are test data, not wire captures.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .protocol.cipher import rekey, unfold, unkeyed_from_fold
from .protocol.frame import Frame

if TYPE_CHECKING:
    from .definitions.model import TubDefinition


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    timestamp: float
    kind: Literal["RX", "MARK"]
    data: bytes = b""
    label: str = ""


def read_capture(
    path: Path, status_type: int = 0xC4, definition: TubDefinition | None = None
) -> Iterator[CaptureRecord]:
    if path.suffix == ".csv":
        yield from _read_decoded_csv(path, status_type, definition)
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            ts, kind, rest = [*line.split(None, 2), "", ""][:3]
            if kind == "RX":
                yield CaptureRecord(float(ts), "RX", data=bytes.fromhex(rest))
            elif kind == "MARK":
                yield CaptureRecord(float(ts), "MARK", label=rest)


def synthetic_status_frame(
    decoded: bytes, key: int, status_type: int = 0xC4, definition: TubDefinition | None = None
) -> bytes:
    """A status frame whose fold equals ``decoded``. With a per-byte definition that has a
    ``fold_template``, the bytes are rebuilt so that per-byte decoding agrees too."""
    if definition is not None and definition.status_decode in ("unkey", "decrypt") and definition.fold_template:
        unkeyed = unkeyed_from_fold(decoded, definition.fold_template, definition.byte_masks())
        payload = rekey(unkeyed, key)
    else:
        payload = unfold(decoded, key=key)
    return Frame(addr=0xFF, mid=0xAF, type=status_type, payload=payload).encode()


def _read_decoded_csv(path: Path, status_type: int, definition: TubDefinition | None) -> Iterator[CaptureRecord]:
    with path.open(newline="") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if not row:
                continue
            decoded = bytes(int(v) for v in row)
            key = (i * 37 + 11) & 0xFF  # deterministic, varies per frame like the real key
            yield CaptureRecord(i * 0.3, "RX", data=synthetic_status_frame(decoded, key, status_type, definition))
