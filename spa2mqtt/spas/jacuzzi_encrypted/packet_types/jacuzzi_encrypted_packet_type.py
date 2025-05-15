from enum import IntEnum


class JacuzziEncryptedPacketType(IntEnum):
    # Common to all Balboa products
    CLIENT_CLEAR_TO_SEND = 0x00
    CHANNEL_ASSIGNMENT_REQ = 0x01
    CHANNEL_ASSIGNMENT_RESPONSE = 0x02
    CHANNEL_ASSIGNMENT_ACK = 0x03
    EXISTING_CLIENT_REQ = 0x04
    EXISTING_CLIENT_RESPONSE = 0x05
    CLEAR_TO_SEND = 0x06
    NOTHING_TO_SEND = 0x07

    # Sundance 780
    STATUS_UPDATE = 0xC4
    LIGHTS_UPDATE = 0xCA
    CC_REQ = 0xCC

    # Jacuzzi
    STATUS_UPDATE_ALT_16 = 0x16
    LIGHTS_UPDATE_ALT_23 = 0x23
    CC_REQ_ALT_17 = 0x17