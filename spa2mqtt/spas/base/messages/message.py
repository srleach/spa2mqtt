from spa2mqtt.spas.base.packet import Packet


class Message():
    """
    A base class to contain common logic for messages from the tub.

    A message is crafted from a packet, where packet represents a raw update from the tub, where messages are
    repsonsible for the actual meaningful content.
    """
    pkt: Packet = None
    message_configuration: list[dict] = []

    def __init__(self, pkt: Packet, message_configuration: list[dict]):
        self.message_configuration = message_configuration
        self.pkt = pkt

    def decode_params(self, schema: list[dict]) -> dict:
        result = {}
        for entry in schema:
            name = entry["name"]
            offset = entry["offset"]
            length = entry.get("length", 1)
            raw = self.pkt.data[offset:offset + length]

            # Convert bytes to int (big endian assumed, customize if needed)
            value = int.from_bytes(raw, byteorder="big")

            # Apply transformations
            if "xor" in entry:
                value ^= entry["xor"]
            if "shift" in entry:
                value = value << entry["shift"] if entry["shift"] > 0 else value >> abs(entry["shift"])
            if "mask" in entry:
                value &= entry["mask"]
            if "scale" in entry:
                value = value * entry["scale"]

            result[name] = value
        return result

