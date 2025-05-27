from enum import IntEnum


class PacketType(IntEnum):
    """
    Define our packet types and the behaviour we know about them.
    """
    # Common to all Balboa products
    DEVICE_PRESENT = 0x04
    TOGGLE_STATE = 0x11
    STATUS_UPDATE = 0x13
    SET_TEMPERATURE = 0x20
    SET_TIME = 0x21
    REQUEST = 0x22
    FILTER_CYCLE = 0x23
    SYSTEM_INFORMATION = 0x24
    SETUP_PARAMETERS = 0x25
    PREFERENCES = 0x26
    SET_TEMPERATURE_UNIT = 0x27
    FAULT_LOG = 0x28
    DEVICE_CONFIGURATION = 0x2E
    SET_WIFI = 0x92
    MODULE_IDENTIFICATION = 0x94

    NOT_DISCOVERED_16 = 0x16
    NOT_DISCOVERED_23 = 0x23
