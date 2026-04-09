from abc import ABC, abstractmethod
from typing import Optional, Type
from enum import IntEnum

__all__ = [
    "Protocol",
    "PlaintextProtocol",
    "JacuzziEncryptedProtocol",
    "get_protocol",
    "PROTOCOL_REGISTRY",
]


class Protocol(ABC):
    @property
    @abstractmethod
    def packet_marker(self) -> int:
        pass

    @property
    @abstractmethod
    def packet_type_enum(self) -> Type[IntEnum]:
        pass

    @abstractmethod
    def decode_body(self, body: bytes) -> list[int]:
        pass

    def decode_packet_type(self, byte: int) -> Optional[IntEnum]:
        try:
            return self.packet_type_enum(byte)
        except ValueError:
            return None


class PlaintextProtocol(Protocol):
    from spa2mqtt.spas.base.packet_types.packet_type import PacketType

    @property
    def packet_marker(self) -> int:
        return 0x7E

    @property
    def packet_type_enum(self) -> Type[IntEnum]:
        return self.PacketType

    def decode_body(self, body: bytes) -> list[int]:
        return list(body)


class JacuzziEncryptedProtocol(Protocol):
    from spa2mqtt.spas.jacuzzi_encrypted.packet_types.jacuzzi_encrypted_packet_type import (
        JacuzziEncryptedPacketType,
    )

    ENCRYPTED_TYPES = {0xC4, 0xCA, 0xCC}

    @property
    def packet_marker(self) -> int:
        return 0x7E

    @property
    def packet_type_enum(self) -> Type[IntEnum]:
        return self.JacuzziEncryptedPacketType

    def _xormsg(self, data: bytes) -> list[int]:
        decoded = []
        for i in range(0, len(data) - 1, 2):
            decoded.append(data[i] ^ data[i + 1] ^ 0x01)
        return decoded

    def decode_body(self, body: bytes) -> list[int]:
        if len(body) > 0 and body[0] in self.ENCRYPTED_TYPES:
            return self._xormsg(body)
        return list(body)


PROTOCOL_REGISTRY = {
    "plaintext": PlaintextProtocol,
    "jacuzzi_encrypted": JacuzziEncryptedProtocol,
}


def get_protocol(protocol_name: str) -> Protocol:
    if protocol_name not in PROTOCOL_REGISTRY:
        raise ValueError(f"Unknown protocol: {protocol_name}")
    return PROTOCOL_REGISTRY[protocol_name]()
