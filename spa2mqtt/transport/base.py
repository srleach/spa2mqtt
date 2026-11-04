"""Transport interface.

Only :class:`spa2mqtt.tub.bus.BusWriter` may call :meth:`Transport.write` (enforced by
tests/test_safety.py). Everything else is read-only.
"""

from __future__ import annotations

from typing import Protocol


class TransmitForbidden(RuntimeError):
    """Raised when something attempts to write while transmitting is not allowed."""


class Transport(Protocol):
    async def connect(self) -> None: ...

    async def read(self) -> bytes:
        """Return the next chunk of received bytes; b"" means end of stream."""
        ...

    async def write(self, data: bytes) -> None: ...

    async def close(self) -> None: ...
