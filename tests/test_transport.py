import pytest
from spa2mqtt.utils.transport import (
    load_class,
    make_tub,
    make_communicator,
    get_communicator,
)


class TestTransport:
    def test_load_class_base_communicator(self):
        cls = load_class("spa2mqtt.spas.base.communicator", "Communicator")
        assert cls.__name__ == "Communicator"

    def test_load_class_jacuzzi_encrypted_communicator(self):
        cls = load_class(
            "spa2mqtt.spas.jacuzzi_encrypted.communicator",
            "JacuzziEncryptedCommunicator",
        )
        assert cls.__name__ == "JacuzziEncryptedCommunicator"

    def test_load_class_base_spa(self):
        cls = load_class("spa2mqtt.spas.base.spa", "Spa")
        assert cls.__name__ == "Spa"

    def test_load_class_jacuzzi_encrypted_spa(self):
        cls = load_class("spa2mqtt.spas.jacuzzi_encrypted.spa", "JacuzziEncryptedSpa")
        assert cls.__name__ == "JacuzziEncryptedSpa"

    def test_make_communicator_with_args(self):
        from spa2mqtt.spas.base.communicator import Communicator

        comm = make_communicator(
            "base", "Communicator", {"spa_address": "192.168.1.1", "spa_port": 8899}
        )
        assert isinstance(comm, Communicator)
        assert comm.spa_address == "192.168.1.1"
        assert comm.spa_port == 8899

    def test_make_communicator_jacuzzi_encrypted(self):
        from spa2mqtt.spas.jacuzzi_encrypted.communicator import (
            JacuzziEncryptedCommunicator,
        )

        comm = make_communicator(
            "jacuzzi_encrypted",
            "JacuzziEncryptedCommunicator",
            {"spa_address": "192.168.25.73", "spa_port": 8899},
        )
        assert isinstance(comm, JacuzziEncryptedCommunicator)

    def test_get_communicator_from_config(self):
        spa_config = {"connection": {"spa_address": "192.168.1.100", "spa_port": 8899}}
        variant_config = {"family": "base", "communicator": "Communicator"}
        comm = get_communicator(spa_config, variant_config)
        assert comm.spa_address == "192.168.1.100"
        assert comm.spa_port == 8899

    def test_get_communicator_jacuzzi(self):
        spa_config = {"connection": {"spa_address": "192.168.25.73", "spa_port": 8899}}
        variant_config = {
            "family": "jacuzzi_encrypted",
            "communicator": "JacuzziEncryptedCommunicator",
        }
        comm = get_communicator(spa_config, variant_config)
        assert comm.spa_address == "192.168.25.73"


class TestSpaConfiguration:
    def test_get_application_configuration_with_file(self):
        from spa2mqtt.utils.spa_configuration import get_application_configuration
        import logging

        config = get_application_configuration(logging.getLogger(), "config.yml")
        assert "spa" in config
        assert "mqtt" in config

    def test_get_variant_configuration_j235(self):
        from spa2mqtt.utils.spa_configuration import get_variant_configuration

        config = get_variant_configuration("jacuzzi_j235_encrypted")
        assert config.get("family") == "jacuzzi_encrypted"
        assert config.get("model_name") == "Jacuzzi J235"

    def test_get_variant_configuration_j335(self):
        from spa2mqtt.utils.spa_configuration import get_variant_configuration

        config = get_variant_configuration("jacuzzi_j335_unencrypted_farenheit")
        assert config.get("family") == "base"
        assert "message_configuration" in config
