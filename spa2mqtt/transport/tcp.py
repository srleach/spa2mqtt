"""TCP client for RS485-to-Ethernet/WiFi bridges such as the EW11A (default port 8899)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket

log = logging.getLogger(__name__)


class TcpTransport:
    def __init__(self, host: str, port: int = 8899, read_timeout: float = 30.0) -> None:
        self.host = host
        self.port = port
        self.read_timeout = read_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            # Replies must land in the CTS slot; don't let Nagle delay them.
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        log.info("connected to %s:%s", self.host, self.port)

    async def read(self) -> bytes:
        if self._reader is None:
            raise ConnectionError("not connected")
        try:
            return await asyncio.wait_for(self._reader.read(4096), timeout=self.read_timeout)
        except TimeoutError as exc:
            raise ConnectionError(f"no data from bridge for {self.read_timeout:.0f}s") from exc

    async def write(self, data: bytes) -> None:  # TRANSMITS (called only by BusWriter)
        if self._writer is None:
            raise ConnectionError("not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(OSError):
                await self._writer.wait_closed()
        self._reader = self._writer = None
