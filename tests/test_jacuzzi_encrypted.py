import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call

from spa2mqtt.spas.jacuzzi_encrypted.packet import JacuzziEncryptedPacket
from spa2mqtt.spas.jacuzzi_encrypted.packet_types import (
    JacuzziEncryptedPacketType,
    JacuzziTopsideControllerButton,
)
from spa2mqtt.spas.jacuzzi_encrypted.spa.jacuzzi_encrypted_spa import (
    JacuzziEncryptedSpa,
)
from spa2mqtt.spas.jacuzzi_encrypted.communicator import JacuzziEncryptedCommunicator
from spa2mqtt.protocols import JacuzziEncryptedProtocol


class TestJacuzziEncryptedPacket:
    def test_packet_construct_basic(self):
        pkt = JacuzziEncryptedPacket.construct_with_params(
            channel=0x10, mid=0xBF, packet_type=0x01, body=bytearray([0xF1, 0x73])
        )
        assert pkt.channel == 0x10
        assert pkt.mid == 0xBF
        assert pkt.packet_type == 0x01

    def test_packet_as_enum_status(self):
        raw = bytes.fromhex("7e0710bfc40102ca7e")
        pkt = JacuzziEncryptedPacket.from_raw(raw)
        assert pkt.as_enum() == JacuzziEncryptedPacketType.STATUS_UPDATE

    def test_packet_as_enum_lights(self):
        raw = bytes.fromhex("7e0710bfca0102e67e")
        pkt = JacuzziEncryptedPacket.from_raw(raw)
        assert pkt.as_enum() == JacuzziEncryptedPacketType.LIGHTS_UPDATE

    def test_packet_as_enum_cc_req(self):
        raw = bytes.fromhex("7e0710bfcce400977e")
        pkt = JacuzziEncryptedPacket.from_raw(raw)
        assert pkt.as_enum() == JacuzziEncryptedPacketType.CC_REQ

    def test_packet_data_decoded(self):
        raw = bytes.fromhex("7e0710bfc40102ca7e")
        pkt = JacuzziEncryptedPacket.from_raw(raw)
        data = pkt.data
        assert isinstance(data, list)

    def test_packet_xormsg(self):
        pkt = JacuzziEncryptedPacket.construct_with_params(
            channel=0x10,
            mid=0xBF,
            packet_type=0xC4,
            body=bytearray([0x01, 0x02, 0x03, 0x04]),
        )
        data = pkt.data
        assert data is not None


class TestJacuzziEncryptedPacketType:
    def test_packet_type_enum_values(self):
        assert JacuzziEncryptedPacketType.STATUS_UPDATE == 0xC4
        assert JacuzziEncryptedPacketType.LIGHTS_UPDATE == 0xCA
        assert JacuzziEncryptedPacketType.CC_REQ == 0xCC

    def test_packet_type_channel_assignment(self):
        assert JacuzziEncryptedPacketType.CHANNEL_ASSIGNMENT_REQ == 0x01
        assert JacuzziEncryptedPacketType.CHANNEL_ASSIGNMENT_ACK == 0x03


class TestJacuzziTopsideControllerButton:
    def test_button_values(self):
        assert JacuzziTopsideControllerButton.BTN_TEMP_UP == 225
        assert JacuzziTopsideControllerButton.BTN_TEMP_DOWN == 226
        assert JacuzziTopsideControllerButton.BTN_P1 == 228
        assert JacuzziTopsideControllerButton.BTN_P2 == 229


class TestJacuzziEncryptedSpa:
    def test_spa_init(self):
        spa = JacuzziEncryptedSpa(
            model="Jacuzzi J235",
            serial_number="TEST123",
            communicator_send_cb=None,
            message_configuration={},
        )
        assert spa.model_name == "Jacuzzi J235"
        assert spa.channel is None

    def test_spa_set_command_temperature(self):
        spa = JacuzziEncryptedSpa(
            model="Jacuzzi J235",
            serial_number="TEST123",
            communicator_send_cb=None,
            message_configuration={},
        )
        assert spa.command_temperature is None
        spa.command_temperature = 38.0
        assert spa.command_temperature == 38.0

    def test_spa_channel_init(self):
        spa = JacuzziEncryptedSpa(
            model="Jacuzzi J235",
            serial_number="TEST123",
            communicator_send_cb=None,
            message_configuration={},
        )
        assert spa.channels_active == []
        assert spa.channel_confidence == 0


class TestJacuzziEncryptedCommunicator:
    def test_communicator_init(self):
        comm = JacuzziEncryptedCommunicator("192.168.25.73", 8899)
        assert comm.spa_address == "192.168.25.73"
        assert comm.spa_port == 8899

    def test_communicator_inherits_base(self):
        from spa2mqtt.spas.base.communicator import Communicator

        assert issubclass(JacuzziEncryptedCommunicator, Communicator)


class TestJacuzziConfig:
    def test_config_loads(self):
        from spa2mqtt.utils.spa_configuration import get_variant_configuration

        config = get_variant_configuration("jacuzzi_j235_encrypted")
        assert config.get("family") == "jacuzzi_encrypted"
        assert config.get("spa") == "JacuzziEncryptedSpa"

    def test_message_configuration_exists(self):
        from spa2mqtt.utils.spa_configuration import get_variant_configuration

        config = get_variant_configuration("jacuzzi_j235_encrypted")
        msg_config = config.get("message_configuration", {})
        assert 0xC4 in msg_config

    def test_temperature_field_config(self):
        from spa2mqtt.utils.spa_configuration import get_variant_configuration

        config = get_variant_configuration("jacuzzi_j235_encrypted")
        msg_config = config.get("message_configuration", {})
        temp_config = next(
            (
                f
                for f in msg_config.get(0xC4, [])
                if f.get("name") == "current_temperature"
            ),
            None,
        )
        assert temp_config is not None
        assert temp_config.get("scale") == 0.5
        assert temp_config.get("offset") == 5
