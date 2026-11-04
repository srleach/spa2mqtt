"""Bus arbitration (docs/protocol.md §4) and the single transmit choke point.

:class:`BusClient` is sans-IO: it consumes received frames and returns frames to send.
:class:`BusWriter` is the only code allowed to write to a transport.
"""

from __future__ import annotations

import logging
from collections import deque
from enum import Enum

from ..definitions.model import BusConfig
from ..protocol.cipher import cc_decode, cc_encode
from ..protocol.frame import Frame
from ..transport.base import TransmitForbidden, Transport

log = logging.getLogger(__name__)

T_NEW_CLIENT_CTS = 0x00
T_CHANNEL_REQUEST = 0x01
T_CHANNEL_RESPONSE = 0x02
T_CHANNEL_ACK = 0x03
T_CTS = 0x06
UNASSIGNED_ADDR = 0xFE
REQUEST_TIMEOUT_FRAMES = 200  # ~ a few seconds of bus traffic


class BusState(Enum):
    LISTEN = "listening"
    CLAIMING = "claiming"
    REQUESTED = "requested"
    READY = "ready"


class BusWriter:
    """The ONLY path from this program to the bus. Refuses unless transmit is enabled."""

    def __init__(self, transport: Transport, enabled: bool) -> None:
        self._transport = transport
        self.enabled = enabled
        self.frames_sent = 0

    async def send(self, frame: Frame) -> None:  # TRANSMITS
        if not self.enabled:
            raise TransmitForbidden(f"transmit disabled; refusing to send {frame}")
        log.info("TX %s", frame)
        await self._transport.write(frame.encode())
        self.frames_sent += 1


class BusClient:
    def __init__(self, config: BusConfig, command_type: int | None, transmit_enabled: bool) -> None:
        self.config = config
        self.command_type = command_type
        self.transmit_enabled = transmit_enabled
        self.state = BusState.LISTEN
        self.channel: int | None = None
        self.polled_channels: set[int] = set()  # addresses the board sends CTS to
        self.active_channels: set[int] = set()  # addresses that answer with commands
        self.commands_seen = 0
        self.queue: deque[int] = deque()
        self._replied_to_last_cts = False
        self._request_age = 0
        self.observed_presses: deque[tuple[int, int]] = deque(maxlen=50)  # (channel, code)

    # -- commands ------------------------------------------------------------

    def enqueue_press(self, code: int) -> None:
        if not self.transmit_enabled or self.command_type is None:
            raise TransmitForbidden("transmit disabled; command not queued")
        self.queue.append(code)
        if self.state is BusState.LISTEN:
            self.state = BusState.CLAIMING
            log.info("command queued; claiming a bus channel")

    # -- receive path ----------------------------------------------------------

    def handle(self, frame: Frame) -> list[Frame]:
        """Observe one received frame; return frames to transmit (empty unless enabled)."""
        out: list[Frame] = []
        if frame.type == T_CTS:
            self.polled_channels.add(frame.addr)
            self._replied_to_last_cts = False
            if self.state is BusState.READY and frame.addr == self.channel and self.queue:
                code = self.queue.popleft()
                out.append(Frame(self.channel, self.config.client_mid, self._command_type(), cc_encode(code)))
                self._replied_to_last_cts = True
        elif self.command_type is not None and frame.type == self.command_type:
            self._observe_command(frame)
        elif (
            frame.type == T_NEW_CLIENT_CTS
            and self.state is BusState.CLAIMING
            and self._dormant() is None
            and self.commands_seen >= self.config.dormant_channel_threshold
        ):
            magic = bytes(self.config.channel_request_magic)
            out.append(Frame(UNASSIGNED_ADDR, self.config.client_mid, T_CHANNEL_REQUEST, b"\x02" + magic))
            self.state = BusState.REQUESTED
            self._request_age = 0
        elif frame.type == T_CHANNEL_RESPONSE and self.state is BusState.REQUESTED and frame.payload:
            self.channel = frame.payload[0]
            out.append(Frame(self.channel, self.config.client_mid, T_CHANNEL_ACK))
            self.state = BusState.READY
            log.info("assigned bus channel 0x%02X", self.channel)

        if self.state is BusState.CLAIMING and self.commands_seen >= self.config.dormant_channel_threshold:
            dormant = self._dormant()
            if dormant is not None:
                self.channel = dormant
                self.state = BusState.READY
                log.info("using dormant bus channel 0x%02X", dormant)
        elif self.state is BusState.REQUESTED:
            self._request_age += 1
            if self._request_age > REQUEST_TIMEOUT_FRAMES:
                log.warning("no channel assignment response; retrying")
                self.state = BusState.CLAIMING
        if not self.transmit_enabled and out:  # defensive: never produce frames when disabled
            out = []
        return out

    def _command_type(self) -> int:
        assert self.command_type is not None
        return self.command_type

    def _observe_command(self, frame: Frame) -> None:
        self.commands_seen += 1
        self.active_channels.add(frame.addr)
        code = cc_decode(frame.payload)
        if code:
            self.observed_presses.append((frame.addr, code))
            log.debug("panel press on 0x%02X: code 0x%02X", frame.addr, code)
        if self.state is BusState.READY and frame.addr == self.channel and not self._replied_to_last_cts:
            log.warning("another device is using channel 0x%02X; releasing it", frame.addr)
            self.channel = None
            self.state = BusState.CLAIMING if self.queue else BusState.LISTEN

    def _dormant(self) -> int | None:
        candidates = sorted(self.polled_channels - self.active_channels - {UNASSIGNED_ADDR, 0xFF})
        return candidates[0] if candidates else None
