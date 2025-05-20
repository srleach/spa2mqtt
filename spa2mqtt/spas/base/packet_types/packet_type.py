from enum import IntEnum


class PacketType(IntEnum):
    """
    Define our packet types and the behaviour we know about them.
    """
    # Common to all Balboa products
    CLIENT_CLEAR_TO_SEND = 0x00
    CHANNEL_ASSIGNMENT_REQ = 0x01
    CHANNEL_ASSIGNMENT_RESPONSE = 0x02
    CHANNEL_ASSIGNMENT_ACK = 0x03
    EXISTING_CLIENT_REQ = 0x04
    EXISTING_CLIENT_RESPONSE = 0x05
    CLEAR_TO_SEND = 0x06
    NOTHING_TO_SEND = 0x07

    NOT_DISCOVERED_16 = 0x16
    NOT_DISCOVERED_23 = 0x23
