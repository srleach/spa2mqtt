import os

import yaml


def get_application_configuration(file: str = 'config.yml'):
    try:
        with open(file, 'r', encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError as err:
        print("Warning: Config file not found. Using some defaults")

        return {
            "spa": {
                "connection": {
                    "spa_address": os.environ.get("SPA_IP", "192.168.1.1"),
                    "spa_port": os.environ.get("SPA_PORT", "8899"),
                },
                "config": os.environ.get("VARIANT_DEFINITION", "jacuzzi_j335_unencrypted_farenheit"),
                "model": "Default Model"
            },
            "mqtt": {
                "broker": os.environ.get("MQTT_BROKER", "192.168.1.7"),
                "port": os.environ.get("MQTT_PORT", "1883"),
            }
        }


def get_variant_configuration(file: str = 'base'):
    with open(f"spa2mqtt/spa_definitions/{file}.yml", 'r', encoding="utf-8") as f:
        return yaml.safe_load(f)
    #TODO handle failure