import asyncio
import datetime
import logging
import sys
from typing import Callable

from spa2mqtt.spas.base.communicator import Communicator


class SimulatedCommunicator(Communicator):
    """
    Communicator to handle interaction with the spa.
    """
    logger: logging.Logger = None

    def __init__(self, spa_address, spa_port, logger: logging.Logger = logging.getLogger(__name__)):
        self.spa_address = spa_address
        self.spa_port = spa_port
        self.logger = logger
        self.logger.info(f"Instantiated simulated communicator with target {spa_address} @ {spa_port}ms")

    def process_update(self, bytes):
        """
        We've received a packet from the spa. Handle it.

        :param bytes:
        :return:
        """
        self.logger.debug(f"Processing message {bytes}")
        return self.spa_process_update_cb(datetime.datetime.now(), bytes)

    async def establish_transport(self):
        """ Connect to the spa."""
        return True

    async def attach_update_handler(self, spa_process_update_cb: Callable[[datetime.datetime, bytes], bool]):
        """
        Attach a callable update handler to the spa.

        :param spa_process_update_cb:
        :return:
        """
        self.logger.info("Attaching update handler.")
        self.spa_process_update_cb = spa_process_update_cb

    async def listen(
            self,
            spa_process_update_cb: Callable[[datetime.datetime, bytes], bool] = None, max_payload_length=128
    ):
        """
        Same argument goes here regarding the specificity of this logic. I'm almost certain that we're going to want
        this to be deviated from depending on the tub in question, but since I don't have another to test against
        we'll consider this the base for the time being. It's likely this will be common to Jacuzzi plaintext/encrypted
        and quite probably balboa boards too. Famous last words...

        :param spa_process_update_cb:
        :param max_payload_length:
        :return:
        """
        await self.attach_update_handler(spa_process_update_cb)
        await self.establish_transport()

        with open(file=self.spa_address, mode='r') as spa_handle:
            # Loop file, with delay, emitting each line as a message.
            for line in spa_handle:
                print(line.strip())
                await asyncio.sleep(int(self.spa_port)/ 1000)

    def send_message_cb(self):
        # print("Sending Message Stub", self.last_packet)
        pass
