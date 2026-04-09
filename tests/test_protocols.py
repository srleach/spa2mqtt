import pytest
from spa2mqtt.protocols import PlaintextProtocol, JacuzziEncryptedProtocol, get_protocol


class TestProtocols:
    def test_plaintext_protocol_packet_marker(self):
        proto = PlaintextProtocol()
        assert proto.packet_marker == 0x7E

    def test_plaintext_protocol_decode_body(self):
        proto = PlaintextProtocol()
        body = bytes([0x01, 0x02, 0x03])
        result = proto.decode_body(body)
        assert result == [1, 2, 3]

    def test_plaintext_protocol_packet_type_enum(self):
        proto = PlaintextProtocol()
        assert proto.packet_type_enum.__name__ == "PacketType"

    def test_jacuzzi_encrypted_protocol_packet_marker(self):
        proto = JacuzziEncryptedProtocol()
        assert proto.packet_marker == 0x7E

    def test_jacuzzi_encrypted_protocol_decode_body_non_encrypted(self):
        proto = JacuzziEncryptedProtocol()
        body = bytes([0x00, 0x01, 0x02])
        result = proto.decode_body(body)
        assert result == [0, 1, 2]

    def test_get_protocol_plaintext(self):
        proto = get_protocol("plaintext")
        assert isinstance(proto, PlaintextProtocol)

    def test_get_protocol_jacuzzi_encrypted(self):
        proto = get_protocol("jacuzzi_encrypted")
        assert isinstance(proto, JacuzziEncryptedProtocol)

    def test_get_protocol_unknown(self):
        with pytest.raises(ValueError):
            get_protocol("unknown")

    def test_decode_packet_type_valid(self):
        proto = PlaintextProtocol()
        result = proto.decode_packet_type(0x23)
        assert result.name == "FILTER_CYCLE"

    def test_decode_packet_type_invalid(self):
        proto = PlaintextProtocol()
        result = proto.decode_packet_type(0xFF)
        assert result is None
