# --- Base Packet class ---
from dataclasses import dataclass
from typing import Optional, TypeVar

from spa2mqtt.spas.base.packet_types import PacketType

T = TypeVar('T', bound=PacketType)


@dataclass
class Packet:
    """
    There's a risk that some of our logic here is becoming quite implementation specific. I think, practically that much
    of this may be better placed in the subclass, but until we've seen other variant tubs I don't know if this format
    is common, rare, etc. For the time being, we'll put message decoding specifics here and only do the enc. stuff
    in the JacuzziEncryptedPacket
    """
    raw: bytes
    channel: int
    len: int
    mid: int
    packet_type: int
    checksum: int
    payload: bytes
    body: bytes

    @property
    def data(self) -> list[int]:
        return list(self.body)

    def as_enum(self) -> Optional[PacketType]:
        try:
            return PacketType(self.packet_type)
        except ValueError:
            return None

    def __repr__(self):
        label = self.as_enum()
        label_str = label.name if label else f"UNKNOWN_{self.packet_type:02X}"
        return (f"<Packet"
                f" {label_str}"
                f" ch=0x{self.channel:02x}"
                f" len={self.len}"
                f" mid=0x{self.mid:02x}"
                f" checksum={self.checksum:02x}"
                f" type=0x{self.packet_type:02x}"
                f" body={self.body.hex()}>"
                f" raw={self.raw.hex()}"
                f">")

    def get_field(self, field):
        return self.data[field]

    @classmethod
    def from_raw(cls, raw: bytes) -> "T":
        if raw[0] != 0x7e or raw[-1] != 0x7e:
            raise ValueError("Invalid framing")

        length = raw[1]
        payload = raw[2:-1]

        if len(payload) < 3:
            raise ValueError("Packet too short to parse")

        channel = raw[2]
        mid = raw[3]
        packet_type = raw[4]
        # is this the right position for the checksum? We should forwards-check this to ensure the packet is valid before
        # scoffing it
        checksum = raw[-2]

        body = raw[5:-2]

        return cls(raw=raw, channel=channel, mid=mid, packet_type=packet_type, payload=raw, len=length,
                   checksum=checksum, body=body)

    def balboa_calc_cs(self, data, length):
        """
        Calculate the checksum byte for a balboa message
        --
        Credit to garbled1

        The CRC is annoying.  Doing CRC's in python is even more annoying than it
        should be.  I hate it.
         * Generated on Sun Apr  2 10:09:58 2017,
         * by pycrc v0.9, https://pycrc.org
         * using the configuration:
         *    Width         = 8
         *    Poly          = 0x07
         *    Xor_In        = 0x02
         *    ReflectIn     = False
         *    Xor_Out       = 0x02
         *    ReflectOut    = False
         *    Algorithm     = bit-by-bit
        https://github.com/garbled1/gnhast/blob/master/balboacoll/collector.c
        """
        crc = 0xb5
        for cur in range(length):
            for i in range(8):
                bit = crc & 0x80
                crc = ((crc << 1) & 0xff) | ((data[cur] >> (7 - i)) & 0x01)
                if (bit):
                    crc = crc ^ 0x07
            crc &= 0xff
        for i in range(8):
            bit = crc & 0x80
            crc = (crc << 1) & 0xff
            if bit:
                crc ^= 0x07
        return crc ^ 0x02
