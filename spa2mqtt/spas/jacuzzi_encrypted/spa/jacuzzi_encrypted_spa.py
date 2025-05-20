import csv
import sys
from datetime import datetime
from typing import Callable

from spa2mqtt.spas.base.spa import Spa
from spa2mqtt.spas.jacuzzi_encrypted.packet import JacuzziEncryptedPacket

# our messages expose the factory and base message entities to us
from spa2mqtt.spas.jacuzzi_encrypted.messages.JacuzziEncryptedMessage import *

DEBUG_MODE = False

class JacuzziEncryptedSpa(Spa):

    def __init__(self, model: str, serial_number: str, communicator_send_cb,
                 message_configuration: dict = {}, mqtt=None, debug: bool = False):

        super().__init__(model=model, serial_number=serial_number, message_configuration=message_configuration, mqtt=mqtt, communicator_send_cb=communicator_send_cb)

        self.debug = debug
        self.communicator_send_cb = communicator_send_cb
        self.message_configuration = message_configuration


        if self.debug:
            print("Debug mode is on")
            self.debug_file = open("debug_messages.csv", "a", newline="")
            self.writer = csv.writer(self.debug_file)

    def process_update(self, timestamp: datetime, payload: bytes):
        """
        We're doing a callback back into the Jacuzzi responsibility here to keep the decoding within the domain of the
        variant. The intention is that for additional spa variants we can expose additional config types that can reuse
        the bulk of the communications logic and simply hand off tub specific logic where required.
        :param timestamp:
        :param payload:
        :return:
        """
        # print(f"Message from {self.model_name} at {timestamp.time().isoformat()}: Len {len(message)}")

        pkt = JacuzziEncryptedPacket(payload)
        message = JacuzziEncryptedMessageFactory.from_packet(pkt, message_configuration=self.message_configuration)

        match pkt.as_enum():
            # This block does not need to be so verbose, but while we're building this out I've stubbed the handling of
            # each message type for the time being.
            case JacuzziEncryptedPacketType.STATUS_UPDATE:
                if DEBUG_MODE:
                    self.writer.writerow(pkt.data)

                # self.mqtt.handle_sensor_updates(message=message)
                pass
            case JacuzziEncryptedPacketType.LIGHTS_UPDATE | JacuzziEncryptedPacketType.LIGHTS_UPDATE_ALT_23:
                pass
            case JacuzziEncryptedPacketType.CLEAR_TO_SEND:
                # In here we'll have to negotiate a channel.
                self.communicator_send_cb()
                pass
            case JacuzziEncryptedPacketType.CC_REQ | JacuzziEncryptedPacketType.CC_REQ_ALT_17:
                pass
            case _:
                print(pkt)
                pass

        # Here's the place to deviate behaviour if we want to selectively process certain packet types. I suppose
        # We should think about implementing a channelising mechanism.
        # print(pkt)
        # <Packet STATUS_UPDATE ch=0x0a mid=0xbf type=0xc4 payload=...>

        return True

