import asyncio
import logging
import sys

from spa2mqtt.mqtt import MQTTControl
from spa2mqtt.utils import get_application_configuration, get_variant_configuration, make_tub
from spa2mqtt.utils.transport import get_communicator


async def main():
    logging.basicConfig(level=logging.INFO)

    application_config = get_application_configuration(logger=logging.getLogger("ConfigManager"))

    spa_configuration = application_config.get('spa', {})
    mqtt_configuration = application_config.get('mqtt', {})

    variant = spa_configuration.get('config', 'base')

    tub_config = get_variant_configuration(variant)

    debug_spa = tub_config.get('debug', False)

    if debug_spa:
        mqtt = None
    else:
        mqtt = MQTTControl(broker_host=mqtt_configuration.get('broker'), broker_port=mqtt_configuration.get('port'),
                           sensor_update_intervals=tub_config.get('sensor_update_intervals', {}))

    communicator = get_communicator(
        spa_configuration=spa_configuration,
        variant_configuration=get_variant_configuration(variant)
    )

    spa = make_tub(
        tub_config.get('family'),
        tub_config.get('spa'),
        get_spa_configuration(communicator, debug_spa, mqtt, spa_configuration, tub_config)
    )

    mqtt.attach_spa(spa)

    await communicator.listen(spa.process_update)


def get_spa_configuration(communicator, debug_spa, mqtt, spaconfig, tub_config):
    configuration = {"message_configuration": tub_config.get('message_configuration'),
                     "model": spaconfig.get('model', tub_config.get('model')),
                     "serial_number": spaconfig.get('serial_number', tub_config.get('serial_number')),
                     'mqtt': mqtt, "communicator_send_cb": communicator.send_message_cb, "debug": debug_spa}
    return configuration


if __name__ == "__main__":
    asyncio.run(main())
