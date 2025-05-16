import asyncio
import logging
import sys

import yaml

from spa2mqtt.spas.jacuzzi_encrypted.communicator import JacuzziEncryptedCommunicator
from spa2mqtt.spas.jacuzzi_encrypted.spa import JacuzziEncryptedSpa
from spa2mqtt.utils import get_application_configuration, make_communicator, get_variant_configuration, make_tub


async def main():
    logging.basicConfig(level=logging.INFO)

    application_config = get_application_configuration()
    spaconfig = application_config.get('spa', {})

    variant = spaconfig.get('config', 'base')

    tub_config = get_variant_configuration(variant)

    communicator = make_communicator(tub_config.get('family'), tub_config.get('communicator'), spaconfig.get('connection'))
    spa = make_tub(tub_config.get('family'), tub_config.get('spa'), tub_config.get('model_name'))

    await communicator.listen(spa.process_update)


if __name__ == "__main__":
    asyncio.run(main())
