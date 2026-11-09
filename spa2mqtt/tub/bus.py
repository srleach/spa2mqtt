"""Bus arbitration (docs/protocol.md §4) and the single transmit choke point.

:class:`BusClient` is sans-IO: it consumes received frames and returns frames to send.
:class:`DirectBusClient` is its sibling for plain boards behind a ProLink module
(docs/protocol-plain.md §5): a fixed address and no channel claim.
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
BOARD_MID = 0xAF
DIRECT_QUEUE_LIMIT = 8
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

    def on_connect(self) -> None:
        """A new transport connection. Channel claims survive a reconnect: nothing to do."""

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


class DirectBusClient:
    """Fixed-address sender for a plain board reached through a ProLink module.

    The ProLink TCP stream carries no clear-to-send and no channel traffic (2,074 captured
    frames, all status or lights), and pyjacuzzi drove the tub by writing straight to the
    socket. So there is nothing to claim: queued frames go out one at a time, spaced
    ``send_gap_frames`` status frames apart. The optional ``hello`` frame is sent once per
    connection, just before the first queued command and never at start-up.
    """

    def __init__(
        self,
        config: BusConfig,
        command_type: int | None,
        transmit_enabled: bool,
        status_type: int,
        hello: Frame | None = None,
    ) -> None:
        if config.client_address is None:
            raise ValueError("direct bus mode needs bus.client_address")
        self.config = config
        self.command_type = command_type
        self.transmit_enabled = transmit_enabled
        self.status_type = status_type
        self.hello = hello
        self.channel: int = config.client_address
        self.state = BusState.READY if transmit_enabled else BusState.LISTEN
        self.queue: deque[Frame] = deque()
        self.replies_seen = 0
        # The monitor reads these from either client. A ProLink stream has no channel traffic.
        self.polled_channels: set[int] = set()
        self.active_channels: set[int] = set()
        self.commands_seen = 0
        self._hello_sent = False
        self._gap = config.send_gap_frames

    def on_connect(self) -> None:
        """A new connection: drop commands queued for the old one and re-arm the hello."""
        if self.queue:
            log.warning("connection restarted; dropping %d queued command(s)", len(self.queue))
            self.queue.clear()
        self._hello_sent = False
        self._gap = self.config.send_gap_frames

    # -- commands ------------------------------------------------------------

    def enqueue_press(self, code: int) -> None:
        if not self.transmit_enabled or self.command_type is None:
            raise TransmitForbidden("transmit disabled; command not queued")
        self.enqueue(Frame(self.channel, self.config.client_mid, self.command_type, bytes([code])))

    def enqueue(self, frame: Frame) -> None:
        if not self.transmit_enabled:
            raise TransmitForbidden("transmit disabled; command not queued")
        if len(self.queue) >= DIRECT_QUEUE_LIMIT:
            log.warning("command queue full (%d); dropping %s", DIRECT_QUEUE_LIMIT, frame)
            return
        self.queue.append(frame)

    # -- receive path ----------------------------------------------------------

    def handle(self, frame: Frame) -> list[Frame]:
        """Observe one received frame; return at most one frame to transmit (none unless enabled)."""
        if frame.addr == self.channel and frame.mid != BOARD_MID:
            self.replies_seen += 1
            log.info("frame addressed to 0x%02X: %s", self.channel, frame)
        if not self.transmit_enabled:
            return []
        if frame.mid != BOARD_MID or frame.type != self.status_type:
            return []
        self._gap += 1
        if not self.queue or self._gap < self.config.send_gap_frames:
            return []
        self._gap = 0
        if self.hello is not None and not self._hello_sent:
            self._hello_sent = True
            return [self.hello]
        return [self.queue.popleft()]
