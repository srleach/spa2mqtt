import logging
import os

import yaml


def get_application_configuration(logger: logging.Logger, file: str = 'config.yml'):
    try:
        with open(file, 'r', encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("Unable to load configuration from file '%s'. Falling back to defaults and environment variables.", file)

        # Define expected env vars and their default values
        env_defaults = {
            "SPA_IP": "192.168.1.1",
            "SPA_PORT": "8899",
            "VARIANT_DEFINITION": "jacuzzi_j335_unencrypted_farenheit",
            "MQTT_BROKER": "192.168.1.7",
            "MQTT_PORT": "1883",
        }

        # Check for any missing (unset or empty) environment variables
        missing_vars = [key for key in env_defaults if not os.environ.get(key)]

        if missing_vars:
            logger.warning(
                "The following environment variables are missing or empty: %s. "
                "Default values will be used. If this is unintentional, please set them.",
                ", ".join(missing_vars)
            )

        # Construct the configuration using environment variables or defaults
        config = {
            "spa": {
                "connection": {
                    "spa_address": os.environ.get("SPA_IP", env_defaults["SPA_IP"]),
                    "spa_port": os.environ.get("SPA_PORT", env_defaults["SPA_PORT"]),
                },
                "config": os.environ.get("VARIANT_DEFINITION", env_defaults["VARIANT_DEFINITION"]),
                "model": "Default Model"
            },
            "mqtt": {
                "broker": os.environ.get("MQTT_BROKER", env_defaults["MQTT_BROKER"]),
                "port": os.environ.get("MQTT_PORT", env_defaults["MQTT_PORT"]),
            }
        }

        return config


def get_variant_configuration(file: str = 'base'):
    with open(f"spa2mqtt/spa_definitions/{file}.yml", 'r', encoding="utf-8") as f:
        return yaml.safe_load(f)
    #TODO handle failure