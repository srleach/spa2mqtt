import pytest
from spa2mqtt.spas.base.packet import Packet


class TestPacket:
    def test_packet_from_raw_valid(self):
        raw = bytes.fromhex("7e0500bfc40102aa7e")
        pkt = Packet.from_raw(raw)
        assert pkt.channel == 0x00
        assert pkt.mid == 0xBF
        assert pkt.packet_type == 0xC4
        assert pkt.cs_pass is True

    def test_packet_from_raw_invalid_framing(self):
        raw = bytes.fromhex("7f0500bfc40102037e")
        with pytest.raises(ValueError, match="Invalid framing"):
            Packet.from_raw(raw)

    def test_packet_checksum_mismatch(self):
        raw = bytes.fromhex("7e0500bfc40102047e")
        with pytest.raises(ValueError, match="Checksum mismatch"):
            Packet.from_raw(raw)

    def test_packet_too_short(self):
        raw = bytes.fromhex("7e0100bf7e")
        with pytest.raises(ValueError, match="Packet too short"):
            Packet.from_raw(raw)

    def test_packet_data_property(self):
        raw = bytes.fromhex("7e0500bfc40102aa7e")
        pkt = Packet.from_raw(raw)
        assert pkt.data == [0x01, 0x02]

    def test_packet_get_field(self):
        raw = bytes.fromhex("7e0500bfc40102aa7e")
        pkt = Packet.from_raw(raw)
        assert pkt.get_field(0) == 0x01

    def test_packet_repr(self):
        raw = bytes.fromhex("7e0500bfc40102aa7e")
        pkt = Packet.from_raw(raw)
        assert "UNKNOWN_C4" in repr(pkt)
