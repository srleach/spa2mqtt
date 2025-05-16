from datetime import datetime

from spa2mqtt.spas.base.packet import Packet
from spa2mqtt.spas.base.packet_types import PacketType


class Spa:
    model_name: str
    message_configuration: dict
    serial_number: str

    def __init__(self, model: str, serial_number: str, message_configuration: dict = {}):
        self.serial_number = serial_number
        self.message_configuration = message_configuration
        self.model_name = model

    def process_update(self, timestamp: datetime, message: bytes):
        """
        We're doing a callback back into the Jacuzzi responsibility here to keep the decoding within the domain of the
        variant. The intention is that for additional spa variants we can expose additional config types that can reuse
        the bulk of the communications logic and simply hand off tub specific logic where required.
        :param timestamp:
        :param message:
        :return:
        """
        pkt = Packet(message)

        match pkt.as_enum():
            case PacketType.STATUS_UPDATE | PacketType.STATUS_UPDATE_ALT_16:
                pass
            case PacketType.CLIENT_CLEAR_TO_SEND:
                pass
            case PacketType.LIGHTS_UPDATE | PacketType.LIGHTS_UPDATE_ALT_23:
                pass
            case PacketType.CLEAR_TO_SEND:
                pass
            case PacketType.CC_REQ | PacketType.CC_REQ_ALT_17:
                pass
            case _:
                print("Spa emitted an unrecognised message")
                print(pkt)

        # Here's the place to deviate behaviour if we want to selectively process certain packet types. I suppose
        # We should think about implementing a channelising mechansim.
        # print(pkt)
        # <Packet STATUS_UPDATE ch=0x0a mid=0xbf type=0xc4 payload=...>

        return True