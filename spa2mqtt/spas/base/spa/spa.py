import csv
from datetime import datetime

from spa2mqtt.spas.base.packet import Packet
from spa2mqtt.spas.base.packet_types import PacketType


class Spa:
    model_name: str
    message_configuration: dict
    serial_number: str
    debug: bool = False

    packets_written: int = 0

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

    def process_update(self, timestamp: datetime, message: bytes):
        """
        We're doing a callback back into the Jacuzzi responsibility here to keep the decoding within the domain of the
        variant. The intention is that for additional spa variants we can expose additional config types that can reuse
        the bulk of the communications logic and simply hand off tub specific logic where required.
        :param timestamp:
        :param message:
        :return:
        """
        # pkt = Packet(message)
        if self.debug:
            self.writer.writerow([timestamp, message.hex()])
            print(f"{timestamp}_: {message.hex()}")
            self.packets_written += 1
            self.debug_file.flush()


        # Here's the place to deviate behaviour if we want to selectively process certain packet types. I suppose
        # We should think about implementing a channelising mechansim.
        # print(pkt)
        # <Packet STATUS_UPDATE ch=0x0a mid=0xbf type=0xc4 payload=...>

        return True
