"""Replay a capture file as if it were the bus. Never writes anywhere."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

from ..captures import CaptureRecord, read_capture
from .base import TransmitForbidden


class ReplayTransport:
    """Feeds RX chunks from a capture (``.log`` raw, or ``.csv`` decoded → synthetic frames).

    ``speed`` 0 replays as fast as possible; 1.0 honours the recorded timestamps.
    """

    def __init__(self, path: str | Path, speed: float = 0.0, status_type: int = 0xC4) -> None:
        self.path = Path(path)
        self.speed = speed
        self.status_type = status_type
        self._records: Iterator[CaptureRecord] | None = None
        self._last_ts: float | None = None
        self.writes_attempted = 0

    async def connect(self) -> None:
        self._records = iter(read_capture(self.path, status_type=self.status_type))

    async def read(self) -> bytes:
        if self._records is None:
            raise ConnectionError("not connected")
        for rec in self._records:
            if rec.kind != "RX":
                continue
            if self.speed > 0 and self._last_ts is not None and rec.timestamp > self._last_ts:
                await asyncio.sleep((rec.timestamp - self._last_ts) / self.speed)
            self._last_ts = rec.timestamp
            return rec.data
        return b""

    @property
    def current_time(self) -> float:
        """Timestamp of the record most recently returned by read() (0 before the first)."""
        return self._last_ts or 0.0

    async def write(self, data: bytes) -> None:
        self.writes_attempted += 1
        raise TransmitForbidden("replay transport is receive-only")

    async def close(self) -> None:
        self._records = None
