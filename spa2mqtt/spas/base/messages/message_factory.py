from spa2mqtt.spas.base.messages.message import Message


class JacuzziUnencryptedMessageFactory:
    _message_map = {}

    @classmethod
    def register(cls, packet_type_enum):
        def decorator(subclass):
            cls._message_map[packet_type_enum] = subclass

            return subclass

        return decorator

    @classmethod
    def from_packet(cls, packet, message_configuration: dict):
        packet_type = packet.as_enum()
        subclass = cls._message_map.get(packet_type, Message)

        # TODO: this could theoretically not be a list
        config: list[dict] = message_configuration.get(int(packet_type), [])

        return subclass(packet, config)
