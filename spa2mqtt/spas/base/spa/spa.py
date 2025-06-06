import csv
from collections import deque
from datetime import datetime
from typing import List

from spa2mqtt.spas.base.messages.message_factory import JacuzziUnencryptedMessageFactory
from spa2mqtt.spas.base.packet import Packet
from spa2mqtt.spas.base.packet_types import PacketType


class Spa:
    model_name: str
    message_configuration: dict
    serial_number: str
    debug: bool = False

    packets_written: int = 0

    send_buffer: deque[Packet] = deque()
    channel_confidence: int = 0
    channels_seen: List[int] = []
    channel: int = None
    channel_requested = False

    CHANNEL_EMPTY_CONFIDENCE_THRESHOLD: int = 5

    def __init__(self, model: str, serial_number: str, communicator_send_cb,
                 message_configuration: dict = {}, mqtt=None, debug: bool = False):

        self.debug = debug
        self.mqtt = mqtt
        self.serial_number = serial_number
        self.message_configuration = message_configuration
        self.model_name = model
        self.communicator_send_cb = communicator_send_cb

        if self.debug:
            filename = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.debug_file = open(f"debug_{filename}.csv", "a", newline="")
            self.writer = csv.writer(self.debug_file)

    async def process_update(self, timestamp: datetime, payload: bytes):
        """
        We're doing a callback back into the Jacuzzi responsibility here to keep the decoding within the domain of the
        variant. The intention is that for additional spa variants we can expose additional config types that can reuse
        the bulk of the communications logic and simply hand off tub specific logic where required.
        :param timestamp:
        :param payload:
        :return:
        """
        if self.debug:
            self.writer.writerow([timestamp, payload.hex()])
            print(f"{timestamp}_: {payload.hex()}")
            self.packets_written += 1
            self.debug_file.flush()

            return True

        pkt = Packet.from_raw(payload)
        message = JacuzziUnencryptedMessageFactory.from_packet(pkt, message_configuration=self.message_configuration)

        # The only deviation from the encrypted packet we need to take is to assert we're paying attention to the MID,
        # Channel and Type - and the type. Our type interpolation on the PacketType enum may not be bang on.

        match pkt.as_enum():
            case PacketType.FILTER_CYCLE:
                print(pkt)
                self.mqtt.handle_sensor_updates(message=message)
            case PacketType.NOT_DISCOVERED_16 | PacketType.NOT_DISCOVERED_23:
                pass
            case _:
                print(pkt)
                pass

        return True
