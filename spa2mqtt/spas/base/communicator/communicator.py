import asyncio
import datetime
import logging
from typing import Callable


class Communicator:
    """
    Communicator to handle interaction with the spa.
    """
    reader: asyncio.StreamReader = None
    writer: asyncio.StreamWriter = None
    last_packet: datetime.datetime = None
    logger: logging.Logger = None

    # Persist our callbacks
    spa_process_update_cb: Callable[[datetime.datetime, bytes], bool]

    packet_marker = 0x7e

    def __init__(self, spa_address, spa_port, logger: logging.Logger = logging.getLogger(__name__)):
        self.spa_address = spa_address
        self.spa_port = spa_port
        self.logger = logger
        self.logger.info(f"Instantiated default communicator with target {spa_address}:{spa_port}")

    def process_update(self, bytes):
        self.logger.debug(f"Processing message {bytes}")
        return self.spa_process_update_cb(datetime.datetime.now(), bytes)

    async def establish_transport(self):
        """ Connect to the spa."""
        if self.reader is not None and self.writer is not None:
            self.logger.info("Already connected...")
            return True

        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.spa_address, self.spa_port
            )

            self.last_packet = datetime.datetime.now()
            self.logger.info("Connected to spa.")
            return True

        except (asyncio.TimeoutError, ConnectionRefusedError):
            self.logger.error("Failed to establish connection to spa.")
            return False

    async def attach_update_handler(self, spa_process_update_cb: Callable[[datetime.datetime, bytes], bool]):
        self.logger.info("Attaching update handler.")
        self.spa_process_update_cb = spa_process_update_cb

    async def _read_valid_start(self):
        """
        There's a fair argument that the logic here might differ between tubs. That said, most examples I've seen online
        seem to share the 0x7e bookend for packet demarcation. We'll leave this here for now, but if we need to abstract
        this into our tub implementations it's trivial to do so at a later time.
        :return:
        """

        prev = None

        while True:
            b = await self.reader.read(1)
            if not b:
                return None, None
            current = b[0]

            if prev == self.packet_marker and current != self.packet_marker:
                return self.packet_marker, current

            prev = current

    async def _read_exactly(self, n: int, timeout: float = 5.0) -> bytes:
        buffer = bytearray()
        while len(buffer) < n:
            try:
                chunk = await asyncio.wait_for(self.reader.read(n - len(buffer)), timeout=timeout)
            except asyncio.TimeoutError:
                raise ValueError(f"Timed out waiting for {n - len(buffer)} more bytes (got {len(buffer)})")
            if not chunk:
                raise ValueError(f"Stream closed early while reading payload (got {len(buffer)} of {n})")
            buffer.extend(chunk)
        return bytes(buffer)

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

        while True:

            # Last Packet Sentinel - we'll do a check here to verify we haven't possibly lost connection with the tub.
            # We'll take some action if so. Likely best destroying this instance and recreating or asserting the conn.

            full_packet = bytes()
            try:
                # Get a valid start marker and length byte
                start, length_byte = await self._read_valid_start()
                if start is None:
                    print("EOF or connection lost.")
                    return

                if length_byte == 0 or length_byte > max_payload_length:
                    continue

                try:
                    full_data = await self._read_exactly(length_byte + 1, timeout=5)
                except ValueError as e:
                    raise e

                payload = full_data[:-1]
                end_marker = full_data[-1]

                if end_marker != self.packet_marker:
                    # In cases of DEBUG logging, we should probably dump this out. We'll logger later TODO
                    continue

                # Valid packet
                full_packet = bytes([self.packet_marker, length_byte]) + payload + bytes([self.packet_marker])

                # Invoke the callback passed from the spa entity.
                self.process_update(full_packet)
                self.last_packet = datetime.datetime.now()

            except Exception as e:

                self.logger.warning(f"{str(e)} when parsing payload {full_packet}")

                continue