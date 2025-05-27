import sys

from spa2mqtt.spas.base.messages.message import Message
from spa2mqtt.spas.jacuzzi_encrypted.messages.JacuzziEncryptedMessageFactory import JacuzziEncryptedMessageFactory
from spa2mqtt.spas.jacuzzi_encrypted.packet_types import JacuzziEncryptedPacketType


@JacuzziEncryptedMessageFactory.register(JacuzziEncryptedPacketType.STATUS_UPDATE)
class JacuzziStatusMessage(Message):
    def parse(self):
        return self.decode_params(self.message_configuration)


@JacuzziEncryptedMessageFactory.register(JacuzziEncryptedPacketType.LIGHTS_UPDATE)
class JacuzziLightsMessage(Message):
    def parse(self):
        # print("Parsing lights message")
        # print(self.pkt.data)
        # logic here
        pass
