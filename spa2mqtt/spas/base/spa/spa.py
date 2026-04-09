import csv
from collections import deque
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from spa2mqtt.spas.base.messages.message_factory import MessageFactory
from spa2mqtt.spas.base.packet import Packet
from spa2mqtt.spas.base.packet_types import PacketType

if TYPE_CHECKING:
    from spa2mqtt.protocols import Protocol


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

    def __init__(
        self,
        model: str,
        serial_number: str,
        communicator_send_cb,
        message_configuration: dict = {},
        mqtt=None,
        debug: bool = False,
        protocol: Optional["Protocol"] = None,
    ):

        self.debug = debug
        self.mqtt = mqtt
        self.serial_number = serial_number
        self.message_configuration = message_configuration
        self.model_name = model
        self.communicator_send_cb = communicator_send_cb
        self.protocol = protocol

        if self.debug:
            filename = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.debug_file = open(f"debug_{filename}.csv", "a", newline="")
            self.writer = csv.writer(self.debug_file)

    async def process_update(self, timestamp: datetime, payload: bytes):
        if self.debug:
            self.writer.writerow([timestamp, payload.hex()])
            print(f"{timestamp}_: {payload.hex()}")
            self.packets_written += 1
            self.debug_file.flush()

            return True

        pkt = Packet.from_raw(payload)
        if self.protocol:
            pkt = pkt.with_protocol(self.protocol)

        message = MessageFactory.from_packet(
            pkt, message_configuration=self.message_configuration
        )

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
