import asyncio
import logging

from spa2mqtt.mqtt import MQTTControl
from spa2mqtt.utils import get_application_configuration, make_communicator, get_variant_configuration, make_tub


async def main():
    logging.basicConfig(level=logging.INFO)

    application_config = get_application_configuration()
    spaconfig = application_config.get('spa', {})
    mqttconfig = application_config.get('mqtt', {})

    variant = spaconfig.get('config', 'base')

    tub_config = get_variant_configuration(variant)

    mqtt = MQTTControl(broker_host=mqttconfig.get('broker'), broker_port=mqttconfig.get('port'),
                       sensor_update_intervals=tub_config.get('sensor_update_intervals', {}))

    communicator = make_communicator(tub_config.get('family'), tub_config.get('communicator'),
                                     spaconfig.get('connection'))

    configuration = {"message_configuration": tub_config.get('message_configuration'),
                     "model": spaconfig.get('model', tub_config.get('model')),
                     "serial_number": spaconfig.get('serial_number', tub_config.get('serial_number')),
                     'mqtt': mqtt, "communicator_send_cb": communicator.send_message_cb}

    spa = make_tub(tub_config.get('family'), tub_config.get('spa'), configuration)

    await communicator.listen(spa.process_update)


if __name__ == "__main__":
    asyncio.run(main())
