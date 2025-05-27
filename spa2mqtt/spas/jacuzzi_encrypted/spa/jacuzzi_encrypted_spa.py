import csv
import logging
from datetime import datetime

from spa2mqtt.spas.base.spa import Spa
from spa2mqtt.spas.jacuzzi_encrypted.packet import JacuzziEncryptedPacket

# our messages expose the factory and base message entities to us
from spa2mqtt.spas.jacuzzi_encrypted.messages.JacuzziEncryptedMessage import *
from spa2mqtt.spas.jacuzzi_encrypted.packet_types import JacuzziTopsideControllerButton

DEBUG_MODE = False


class JacuzziEncryptedSpa(Spa):
    last_outbound = 0
    channels_active = []
    command_temperature: float = None
    command_hysteresis_control = 0
    target_match_count = 0
    requested_new_channel = False

    def __init__(self, model: str, serial_number: str, communicator_send_cb,
                 message_configuration: dict = {}, mqtt=None, debug: bool = False, logger: logging.Logger = None):

        super().__init__(model=model, serial_number=serial_number, message_configuration=message_configuration,
                         mqtt=mqtt, communicator_send_cb=communicator_send_cb)

        self.debug = debug
        self.communicator_send_cb = communicator_send_cb
        self.message_configuration = message_configuration

        self.logger = logger or logging.getLogger(f"jacuzzi2mqtt_spas.{__name__}")

        if self.debug:
            self.logger.warning("Debug mode is on")
            self.debug_file = open(f"{datetime.now().timestamp()}-debug_messages.csv", "a", newline="")
            self.writer = csv.writer(self.debug_file)

    def queue_packet(self, packet: JacuzziEncryptedPacket):
        self.send_buffer.append(packet)

    async def claim_channel_when_ready(self, packet: JacuzziEncryptedPacket):
        if packet.channel not in self.channels_active:
            self.channels_active.append(packet.channel)

        self.channel_confidence += 1

        if self.channel_confidence >= self.CHANNEL_EMPTY_CONFIDENCE_THRESHOLD and not self.channel_requested:

            self.channel = next((x for x in sorted(self.channels_seen) if x not in set(self.channels_active)), None)
            if self.channel is not None:
                self.channel_requested = True
                self.logger.info(f'Claimed open and dormant channel {self.channel}')

            if self.channel is None and self.requested_new_channel is False:
                await self.request_channel()
                self.requested_new_channel = True
                return False

        return True

    async def request_channel(self):
        self.logger.debug(f'Requesting new channel from controller')
        data = bytearray([0xF1, 0x73])
        channel_request_packet = JacuzziEncryptedPacket.construct_with_params(mid=0xFE, channel=0xBF, packet_type=0x01, body=data)
        await self.communicator_send_cb(channel_request_packet.raw)

    async def ack_channel(self, channel: int):
        self.logger.debug(f'Ack channel {channel}')
        data = bytearray([])
        channel_ack_packet = JacuzziEncryptedPacket.construct_with_params(
            mid=0xBF,
            channel=channel,
            packet_type=JacuzziEncryptedPacketType.CHANNEL_ASSIGNMENT_ACK,
            body=data
        )
        await self.communicator_send_cb(channel_ack_packet.raw)

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

    async def send_queued_message(self):
        if self.channel is None:
            return True

        if not self.send_buffer:
            return True

        packet = self.send_buffer.popleft()

        await self.communicator_send_cb(packet.raw)

    async def queue_button_command(self, button: int, send_immediately: bool = False):
        """
        Queue a button command. In some cases, we'd like this to skip the queue. Use send_immediately if you want that.
        :param send_immediately:
        :param button:
        :return:
        """
        data = bytearray([button, 0])
        btn_packet = JacuzziEncryptedPacket.construct_with_params(
            mid=0xBF,
            channel=self.channel,
            packet_type=JacuzziEncryptedPacketType.CC_REQ,
            body=data
        )

        if send_immediately:
            self.queue_packet(btn_packet)
        else:
            await self.communicator_send_cb(btn_packet.raw)

    async def set_command_temperature(self, temperature: float):
        self.command_temperature = float(temperature)

    async def process_update(self, timestamp: datetime, payload: bytes):
        """
        We're doing a callback back into the Jacuzzi responsibility here to keep the decoding within the domain of the
        variant. The intention is that for additional spa variants we can expose additional config types that can reuse
        the bulk of the communications logic and simply hand off tub specific logic where required.
        :param timestamp:
        :param payload:
        :return:
        """
        pkt = JacuzziEncryptedPacket.from_raw(payload)
        message = JacuzziEncryptedMessageFactory.from_packet(pkt, message_configuration=self.message_configuration)

        match pkt.as_enum():

            # This block does not need to be so verbose, but while we're building this out I've stubbed the handling of
            # each message type for the time being.
            case JacuzziEncryptedPacketType.STATUS_UPDATE:
                await self.do_command_loop(message=message)
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
                await self.claim_channel_when_ready(pkt)

                pass
            case JacuzziEncryptedPacketType.CHANNEL_ASSIGNMENT_RESPONSE:
                # Also I've just realised that we'll ack the Chan response to any device on the bus with this.
                # Should probably be selective.
                await self.ack_channel(pkt.get_field(0))
            case _:
                self.logger.debug(f"Received a message using an unhandled packet type {pkt.as_enum()}.")
                pass

        return True

    async def do_command_loop(self, message: Message):
        # This is temporarily only concerned with temp. We may want to change this for declarative control of pumps.

        if self.command_temperature is None:
            return

        if self.command_hysteresis_control != 1:
            commands = int((self.command_temperature - message.parse().get('setpoint_temperature')) / 0.5)
            self.logger.debug(f"Requires {commands} to hit target temperature")

            if commands > 0:
                btn = JacuzziTopsideControllerButton.BTN_TEMP_UP
            else:
                btn = JacuzziTopsideControllerButton.BTN_TEMP_DOWN

            for _ in range(abs(commands)):
                await self.queue_button_command(btn)

            self.command_hysteresis_control = 1

            return True

        self.target_match_count += 1

        if self.target_match_count > 3:
            # We're now set, or something's awry
            self.logger.debug("Stability threshold met")

            if self.command_temperature == message.parse().get('setpoint_temperature'):
                self.command_temperature = None
                self.logger.debug("Target reached")

            self.target_match_count = 0
            self.command_hysteresis_control = 0

        return True
