"""Direct serial (USB-RS485 adapter). Requires the optional ``serial`` extra."""

from __future__ import annotations

import asyncio
from typing import Any


class SerialTransport:
    def __init__(self, device: str, baud: int = 115200) -> None:
        self.device = device
        self.baud = baud
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        try:
            import serial_asyncio  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("install spa2mqtt[serial] for serial transport") from exc
        opened: Any = await serial_asyncio.open_serial_connection(url=self.device, baudrate=self.baud)
        self._reader, self._writer = opened

    async def read(self) -> bytes:
        if self._reader is None:
            raise ConnectionError("not connected")
        return await self._reader.read(4096)

    async def write(self, data: bytes) -> None:  # TRANSMITS (called only by BusWriter)
        if self._writer is None:
            raise ConnectionError("not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._reader = self._writer = None
