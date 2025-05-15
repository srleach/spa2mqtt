from typing import Optional

from spa2mqtt.spas.base.packet import Packet
from spa2mqtt.spas.jacuzzi_encrypted.packet_types import JacuzziEncryptedPacketType


class JacuzziEncryptedPacket(Packet):
    """
    This encrypted packet extends our base packet with specifics to the jacuzzi variant - handles decoding, and
    later we'll update this to expose a creation mechanism that doesn't require us to manually build the payload and
    encode or encrypt it if necessary.
    """
    ENCRYPTED_PACKET_TYPES = {
        JacuzziEncryptedPacketType.STATUS_UPDATE,
        JacuzziEncryptedPacketType.LIGHTS_UPDATE,
        JacuzziEncryptedPacketType.CC_REQ
    }

    def as_enum(self) -> Optional[JacuzziEncryptedPacketType]:
        try:
            return JacuzziEncryptedPacketType(self.packet_type)
        except ValueError:
            return None

    def xormsg(self, data: bytes) -> list[int]:
        decoded = []
        for i in range(0, len(data) - 1, 2):
            decoded.append(data[i] ^ data[i + 1] ^ 0x01)
        return decoded

    def __init__(self, raw: bytes):
        pkt = Packet.from_raw(raw)
        super().__init__(**pkt.__dict__)

    @property
    def data(self) -> list[int]:
        if self.as_enum() in self.ENCRYPTED_PACKET_TYPES:
            # Use same logic: slice encrypted body from raw
            return self.xormsg(self.raw[7:-2])
        return list(self.payload)