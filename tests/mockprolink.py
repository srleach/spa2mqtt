"""An in-process stand-in for a J345 behind a ProLink module, for testing the direct transmit path.

Nothing here touches a real bus. It models only what the pyjacuzzi session capture (S,
tests/fixtures/captures/unencrypted/2025-05-21_pyjacuzzi_prolink_session.txt) shows: plain
0x16 status about three times per 0x23 lights frame, no clear-to-send, and the tub's visible
reaction to the commands that capture contains.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spa2mqtt.protocol import Frame

PROLINK = 0x0A
# S L5: 19:34, Wed 21 May 2025, water 100 °F, setpoint 80 °F, everything off.
STATUS_TEMPLATE = bytes.fromhex("1322750519080064fa5000000002000066011c016c8000800000000000000000")
# RGB the tub reported for each commanded mode (S L27-L55).
MODE_RGB = {
    1: (0x55, 0x55, 0x55),
    2: (0x00, 0x00, 0xFF),
    3: (0x00, 0xFF, 0x00),
    4: (0x7F, 0x7F, 0x00),
    5: (0xAA, 0x55, 0x00),
    6: (0xFF, 0x00, 0x00),
    7: (0x7F, 0x00, 0x7F),
    8: (0x92, 0x6D, 0x00),
    9: (0x00, 0x7F, 0x7F),
}


@dataclass
class MockProlink:
    setpoint: int = 0x50
    pump1: bool = False
    pump2: bool = False
    light_mode: int = 0
    light_brightness: int = 0
    received: list[Frame] = field(default_factory=list)
    cycles: int = 0

    def status(self) -> Frame:
        p = bytearray(STATUS_TEMPLATE)
        p[9] = self.setpoint
        p[10] = (0x08 if self.pump1 else 0) | (0x20 if self.pump2 else 0)
        return Frame(0xFF, 0xAF, 0x16, bytes(p))

    def lights(self) -> Frame:
        record = bytes(7)
        if self.light_mode:
            record = bytes([self.light_mode, 0, self.light_brightness, *MODE_RGB[self.light_mode], 0])
        return Frame(0xFF, 0xAF, 0x23, record * 4)

    def cycle(self) -> list[Frame]:
        """About one second of traffic: three status frames, then one lights frame."""
        self.cycles += 1
        return [self.status(), self.status(), self.status(), self.lights()]

    def receive(self, frame: Frame) -> list[Frame]:
        """A frame the client transmitted. Returns the tub's immediate replies."""
        self.received.append(frame)
        assert (frame.addr, frame.mid) == (PROLINK, 0xBF), frame
        p = frame.payload
        if frame.type == 0x19:
            return [Frame(PROLINK, 0xBF, 0x1B, bytes([0x13, 0x0C]))]  # S L4
        if frame.type == 0x20:
            self.setpoint = p[0]
        elif frame.type == 0x17 and p[0] == 0x04:
            self.pump1 = not self.pump1
        elif frame.type == 0x17 and p[0] == 0x05:
            self.pump2 = not self.pump2
        elif frame.type == 0x21 and p[0] == 0x1F:  # colour; brightness keeps or defaults to 60
            self.light_mode = p[1]
            self.light_brightness = self.light_brightness or 0x3C
        elif frame.type == 0x21 and p[0] == 0x2F:  # brightness; 0 switches every record off
            if p[6] == 0:
                self.light_mode = self.light_brightness = 0
            elif self.light_mode:
                self.light_brightness = p[6]
        else:
            raise AssertionError(f"the capture shows no such command: {frame}")
        return []
