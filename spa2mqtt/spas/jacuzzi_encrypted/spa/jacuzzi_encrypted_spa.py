import csv
import sys
from datetime import datetime
from typing import Callable

from spa2mqtt.spas.base.packet import Packet
from spa2mqtt.spas.base.spa import Spa
from spa2mqtt.spas.jacuzzi_encrypted.messages import JacuzziEncryptedMessage
from spa2mqtt.spas.jacuzzi_encrypted.packet import JacuzziEncryptedPacket

# our messages expose the factory and base message entities to us
from spa2mqtt.spas.jacuzzi_encrypted.messages.JacuzziEncryptedMessage import *
from spa2mqtt.spas.jacuzzi_encrypted.packet_types import JacuzziTopsideControllerButton

DEBUG_MODE = False


class JacuzziEncryptedSpa(Spa):
    last_outbound = 0
    channels_active = []

    def __init__(self, model: str, serial_number: str, communicator_send_cb,
                 message_configuration: dict = {}, mqtt=None, debug: bool = False):

        super().__init__(model=model, serial_number=serial_number, message_configuration=message_configuration,
                         mqtt=mqtt, communicator_send_cb=communicator_send_cb)

        self.debug = debug
        self.communicator_send_cb = communicator_send_cb
        self.message_configuration = message_configuration

        if self.debug:
            print("Debug mode is on")
            self.debug_file = open("debug_messages.csv", "a", newline="")
            self.writer = csv.writer(self.debug_file)

    def queue_packet(self, packet: JacuzziEncryptedPacket):
        self.send_buffer.append(packet)

    def claim_channel_when_ready(self, packet: JacuzziEncryptedPacket):
        if packet.channel not in self.channels_active:
            self.channels_active.append(packet.channel)

        self.channel_confidence += 1

        if self.channel_confidence >= self.CHANNEL_EMPTY_CONFIDENCE_THRESHOLD and not self.channel_requested:
            # await self.request_channel()
            self.channel_requested = True
            self.channel = next((x for x in sorted(self.channels_seen) if x not in set(self.channels_active)), None)
            print(f"Got Channel: {self.channel}")

        return True

    async def can_send(self, packet: JacuzziEncryptedPacket):
        """
        We can almost certainly move this up to the base. This will assert we have a channel and return None if we
        are not set. We can use the return of this method to control whether we move on to emit contents from the buffer
        :param packet:
        :return:
        """
        if packet.packet_type != JacuzziEncryptedPacketType.CLEAR_TO_SEND:
            raise Exception("Channel preparation is not concerned with non-cts packets")

        # Log this channel if we haven't already
        if packet.channel not in self.channels_seen:
            self.channels_seen.append(packet.channel)

        if packet.channel == self.channel:
            return True

        return False

    async def request_channel(self):
        """
        We don't actually need to call this if there's a seemingly dormant channel already seen with no activity - we'll
        just claim that instead.
        :return:
        """
        data = bytearray([0xF1, 0x73])
        channel_request_packet = JacuzziEncryptedPacket.construct_with_params(mid=0xFE, channel=0xBF, packet_type=0x01,
                                                                              body=data)

        # We want to emit this directly, without queuing in this circumstance
        await self.communicator_send_cb(channel_request_packet.raw)

    async def ack_channel(self, channel: int):
        data = bytearray([])
        channel_ack_packet = JacuzziEncryptedPacket.construct_with_params(
            mid=0xBF,
            channel=channel,
            packet_type=JacuzziEncryptedPacketType.CHANNEL_ASSIGNMENT_ACK,
            body=data
        )

        # We want to emit this directly, without queuing in this circumstance
        await self.communicator_send_cb(channel_ack_packet.raw)

        self.channel = channel
        print(f"Channel {channel} claimed.")
        return True

    async def send_queued_message(self):
        if self.channel is None:
            return True

        if not self.send_buffer:
            return True

        packet = self.send_buffer.popleft()

        await self.communicator_send_cb(packet.raw)

    def queue_button_command(self, button: int):
        """
        We'll need to do something about the button int - let's IntEnum it later. TODO
        :param button:
        :return:
        """
        print(f"Attempting to send button command {button}")
        data = bytearray([button, 0])
        btn_packet = JacuzziEncryptedPacket.construct_with_params(
            mid=0xBF,
            channel=self.channel,
            packet_type=JacuzziEncryptedPacketType.CC_REQ,
            body=data
        )

        self.queue_packet(btn_packet)

    async def process_update(self, timestamp: datetime, payload: bytes):
        """
        We're doing a callback back into the Jacuzzi responsibility here to keep the decoding within the domain of the
        variant. The intention is that for additional spa variants we can expose additional config types that can reuse
        the bulk of the communications logic and simply hand off tub specific logic where required.
        :param timestamp:
        :param payload:
        :return:
        """
        # print(f"Message from {self.model_name} at {timestamp.time().isoformat()}: Len {len(message)}")

        pkt = JacuzziEncryptedPacket.from_raw(payload)
        message = JacuzziEncryptedMessageFactory.from_packet(pkt, message_configuration=self.message_configuration)

        # if False:
        #     ts = datetime.now().timestamp()
        #
        #     if ts - self.last_outbound > 1:
        #         self.last_outbound = ts
        #         if self.channel is not None:
        #             self.queue_button_command(JacuzziTopsideControllerButton.BTN_TEMP_UP)

        match pkt.as_enum():

            # This block does not need to be so verbose, but while we're building this out I've stubbed the handling of
            # each message type for the time being.
            case JacuzziEncryptedPacketType.STATUS_UPDATE:
                if DEBUG_MODE:
                    self.writer.writerow(pkt.data)

                self.mqtt.handle_sensor_updates(message=message)
                pass
            case JacuzziEncryptedPacketType.LIGHTS_UPDATE | JacuzziEncryptedPacketType.LIGHTS_UPDATE_ALT_23:
                pass
            case JacuzziEncryptedPacketType.CLEAR_TO_SEND:
                can_send = await self.can_send(pkt)

                if can_send:
                    await self.send_queued_message()
                pass
            case JacuzziEncryptedPacketType.CLIENT_CLEAR_TO_SEND:
                pass
            case JacuzziEncryptedPacketType.CC_REQ | JacuzziEncryptedPacketType.CC_REQ_ALT_17:
                """
                We've received a message from another device in the bus. This is intended for the board, but we may 
                wish to carry out some actions as a result.
                
                We'll use this message to build a representation of devices on the network in order to claim a channel,
                while reusing a dormant one if available.
                """
                self.claim_channel_when_ready(pkt)

                pass
            case JacuzziEncryptedPacketType.CHANNEL_ASSIGNMENT_RESPONSE:
                # Let's not magic number this.
                # Also I've just realised that we'll ack the Chan response to any device on the bus with this.
                # Should probably be selective.
                print("WARNING: Received CHAN ASSIGNMENT response, this is currently skipped.")
                # await self.ack_channel(pkt.get_field(0))
            case _:
                # print(pkt)
                pass

        # Here's the place to deviate behaviour if we want to selectively process certain packet types. I suppose
        # We should think about implementing a channelising mechanism.
        # print(pkt)
        # <Packet STATUS_UPDATE ch=0x0a mid=0xbf type=0xc4 payload=...>

        return True
