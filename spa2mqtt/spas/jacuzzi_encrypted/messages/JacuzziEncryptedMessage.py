import sys

from spa2mqtt.spas.base.messages.message import Message
from spa2mqtt.spas.jacuzzi_encrypted.messages.JacuzziEncryptedMessageFactory import JacuzziEncryptedMessageFactory
from spa2mqtt.spas.jacuzzi_encrypted.packet_types import JacuzziEncryptedPacketType


@JacuzziEncryptedMessageFactory.register(JacuzziEncryptedPacketType.STATUS_UPDATE)
class JacuzziStatusMessage(Message):
    current_temperature: float = None
    PARAM_DECODE_SCHEMA = [ # Aim is to pull this into yml config on a per-tub basis.
        {
            "name": "current_temperature",
            "offset": 5,
            "length": 1,
            "xor": 0x02,
            "scale": 0.5 # This will vary if we're in F or C
        },
        {
            "name": "water_life_remaining",
            "offset": 12,
            "length": 1,

        },
        {
            "name": "filter_life_remaining",
            "offset": 3,
            "length": 1,
        },
        # {
        #     "name": "lights_on",
        #     "offset": 5,
        #     "length": 1,
        #     "mask": 0b00000001
        # }
    ]

    def parse(self):
        print(self.decode_params(self.PARAM_DECODE_SCHEMA))
        # logic here
        pass


@JacuzziEncryptedMessageFactory.register(JacuzziEncryptedPacketType.LIGHTS_UPDATE)
class JacuzziLightsMessage(Message):
    def parse(self):
        print("Parsing lights message")
        print(self.pkt.data)
        # logic here
        pass
