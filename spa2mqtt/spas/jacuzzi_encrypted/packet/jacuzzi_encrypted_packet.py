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
        """
        Sourced from HyperactiveJ
        :param data:
        :return:
        """
        decoded = []
        for i in range(0, len(data) - 1, 2):
            decoded.append(data[i] ^ data[i + 1] ^ 0x01)
        return decoded
    #
    # def __init__(self, raw: bytes):
    #     pkt = Packet.from_raw(raw)
    #     super().__init__(**pkt.__dict__)


    @classmethod
    def construct_with_params(cls, channel: int, mid: int, packet_type: int, body: bytearray):
        packet_data = bytearray()

        packet_data.append(cls.PACKET_DELIMITER)
        packet_data.append(len(body) + 5)
        packet_data.append(channel)
        packet_data.append(mid)
        packet_data.append(packet_type)
        packet_data.extend(body)
        packet_data.append(cls.calculate_checksum(packet_data[1:]))
        packet_data.append(cls.PACKET_DELIMITER)

        return cls.from_raw(packet_data)

    @property
    def data(self) -> list[int]:
        if self.as_enum() in self.ENCRYPTED_PACKET_TYPES:
            # Use same logic: slice encrypted body from raw
            return self.xormsg(self.body)

        return list(self.body)