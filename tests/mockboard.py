"""An in-process simulation of the J235 board and topside, for testing the transmit path.

Nothing here touches a real bus. The model follows docs/protocol.md: CTS polling of channel
0x10 (the topside, which answers every CTS), a new-client 0x00 poll, channel assignment on
request, C4 status, and set-mode behaviour for temperature presses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spa2mqtt.definitions import load_definition
from spa2mqtt.protocol import Frame, cc_decode, cc_encode, decrypt, rekey

TOPSIDE = 0x10
# Unkeyed J235 payload (D1), the base the mock writes its per-byte fields into.
TEMPLATE = bytes.fromhex("000c04050a0e77f30b0f400f321390145a17140c1a1b3b19af1f1c504363202126")
_STREAM = load_definition("jacuzzi_j235").status_stream
assert _STREAM is not None
PLAIN_TEMPLATE = decrypt(TEMPLATE, _STREAM)  # TEMPLATE has key 0, so decrypt == unkey ^ stream


@dataclass
class MockBoard:
    setpoint_raw: int = 0x4D  # 38.5 °C
    water_raw: int = 0x4D
    pump1: int = 0
    pump2: bool = False
    set_mode_frames: int = 0
    assigned: list[int] = field(default_factory=list)
    next_channel: int = 0x11
    polled: list[int] = field(default_factory=lambda: [TOPSIDE])
    presses: list[tuple[int, int]] = field(default_factory=list)
    acked: list[int] = field(default_factory=list)
    ignore_presses: int = 0  # simulate presses lost on the bus
    new_client_poll_after: int = 0  # suppress the 0x00 poll for this many cycles (slow channel grant)
    cycles: int = 0

    def status(self) -> Frame:
        """A J235 status frame built from plaintext (docs/protocol.md §3.3)."""
        p = bytearray(PLAIN_TEMPLATE)
        p[1] = 21  # hour
        p[2] = (p[2] & ~0x40) | (0x40 if self.pump1 else 0)  # pump 1 running
        p[3] = (p[3] & ~0x04) | (0x04 if self.pump2 else 0)  # pump 2
        p[5] = 3 | (self.pump1 << 3) | (0x20 if self.set_mode_frames else 0)
        p[10] = self.water_raw
        p[16] = self.setpoint_raw
        p[19] = 26
        assert _STREAM is not None
        unkeyed = bytes(a ^ b for a, b in zip(p, _STREAM, strict=True))
        return Frame(0xFF, 0xAF, 0xC4, rekey(unkeyed, key=0x5A))

    def cycle(self) -> list[Frame]:
        """One bus cycle: a CTS (and the topside's idle reply) per polled channel, a 0x00, a status."""
        out: list[Frame] = []
        for ch in self.polled:
            out.append(Frame(ch, 0xBF, 0x06))
            if ch == TOPSIDE:
                out.append(Frame(TOPSIDE, 0xBF, 0xCC, cc_encode(0x00, key=0x33)))
        self.cycles += 1
        if self.cycles > self.new_client_poll_after:
            out.append(Frame(0xFE, 0xBF, 0x00))
        if self.set_mode_frames:
            self.set_mode_frames -= 1
        out.append(self.status())
        return out

    def receive(self, frame: Frame) -> list[Frame]:
        """Frames the client transmitted. Returns the board's immediate replies."""
        if frame.type == 0x01 and frame.addr == 0xFE:
            ch = self.next_channel
            self.next_channel += 1
            self.assigned.append(ch)
            return [Frame(0xFE, 0xBF, 0x02, bytes([ch]))]
        if frame.type == 0x03:
            self.acked.append(frame.addr)
            if frame.addr not in self.polled:
                self.polled.append(frame.addr)
            return []
        if frame.type == 0xCC:
            code = cc_decode(frame.payload)
            assert code is not None
            self.presses.append((frame.addr, code))
            if self.ignore_presses:
                self.ignore_presses -= 1
                return []
            self.apply(code)
        return []

    def apply(self, code: int) -> None:
        if code in (0x01, 0x02):
            if self.set_mode_frames:
                self.setpoint_raw += 1 if code == 0x01 else -1
            self.set_mode_frames = 15  # ≈ 5 s at 3.3 Hz
        elif code == 0x04:
            self.pump1 = (self.pump1 + 1) % 3
        elif code == 0x05:
            self.pump2 = not self.pump2
