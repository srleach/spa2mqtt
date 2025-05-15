# --- Base Packet class ---
from dataclasses import dataclass
from typing import Optional, TypeVar

from spa2mqtt.spas.base.packet_types import PacketType

T = TypeVar('T', bound=PacketType)

@dataclass
class Packet:
    raw: bytes
    channel: int
    mid: int
    packet_type: int
    payload: bytes

    def as_enum(self) -> Optional[PacketType]:
        try:
            return PacketType(self.packet_type)
        except ValueError:
            return None

    def __repr__(self):
        label = self.as_enum()
        label_str = label.name if label else f"UNKNOWN_{self.packet_type:02X}"
        return (f"<Packet {label_str} ch=0x{self.channel:02x} mid=0x{self.mid:02x} "
                f"type=0x{self.packet_type:02x} payload={self.payload.hex()}>")

    @classmethod
    def from_raw(cls, raw: bytes) -> "T":
        if raw[0] != 0x7e or raw[-1] != 0x7e:
            raise ValueError("Invalid framing")

        length = raw[1]
        payload = raw[2:-1]

        if len(payload) < 3:
            raise ValueError("Packet too short to parse")

        channel = payload[0]
        mid = payload[1]
        packet_type = payload[2]
        data = payload[3:]

        return cls(raw=raw, channel=channel, mid=mid, packet_type=packet_type, payload=data)
