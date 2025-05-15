import asyncio
import logging

from spa2mqtt.spas.jacuzzi_encrypted.communicator import JacuzziEncryptedCommunicator
from spa2mqtt.spas.jacuzzi_encrypted.spa import JacuzziEncryptedSpa


async def main():
    logging.basicConfig(level=logging.INFO)

    jacuzzi_communicator = JacuzziEncryptedCommunicator('192.168.25.73', 8899)
    spa = JacuzziEncryptedSpa("Jacuzzi J235")

    print(spa, jacuzzi_communicator)

    print("Stub")

    await jacuzzi_communicator.listen(spa.process_update)


if __name__ == "__main__":
    asyncio.run(main())
