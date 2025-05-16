from spa2mqtt.spas.base.messages.message import Message

# This might result in circular dependency, but we need our decorators to be executed.



class JacuzziEncryptedMessageFactory:
    _message_map = {}

    @classmethod
    def register(cls, packet_type_enum):
        def decorator(subclass):
            cls._message_map[packet_type_enum] = subclass

            return subclass

        return decorator

    @classmethod
    def from_packet(cls, packet):
        packet_type = packet.as_enum()
        subclass = cls._message_map.get(packet_type, Message)
        return subclass(packet)
