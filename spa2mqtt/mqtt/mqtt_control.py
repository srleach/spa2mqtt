import logging
from logging import Logger

from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo, BinarySensorInfo, BinarySensor, LightInfo, Light, \
    ButtonInfo, Button
from paho.mqtt.client import MQTTMessage, Client


class MQTTControl:
    skip_config_ids = []
    entities = {}  # Persistence
    spa = None

    def __init__(self, logger: Logger = None, broker_host="localhost", broker_port=1883, device="Jacuzzi J235",
                 device_id="185569045"):
        self.mqtt_settings = Settings.MQTT(host=broker_host, port=broker_port)
        self.device_name = device
        self.device_id = device_id
        self.logger = logger or logging.getLogger(self.device_name)

    # Configure the required parameters for the MQTT broker

    def get_device_info(self) -> DeviceInfo:
        # Define the device. At least one of `identifiers` or `connections` must be supplied
        return DeviceInfo(
            name=self.device_name,
            identifiers=self.device_id,
            manufacturer=self.device_name,
            model=self.device_id,
        )

    def button_callback(self, client, userdata, message):
        # print(message.topic, userdata)
        # self.logger.info(f"Received button callback on topic: {message.topic}")
        #
        # method_name = userdata['call']
        # method = getattr(self.spa, method_name)
        # asyncio.run(method(**userdata['args']))
        pass

    def light_callback(self, client: Client, user_data, message: MQTTMessage):
        pass

    def sensor(self, id, sensor_config, value, as_binary=False):
        if id in self.entities:
            sensor = self.entities[id]
        else:
            params = {**sensor_config, **{"device": self.get_device_info()}, "unique_id": id}
            sensor_info = BinarySensorInfo(**params) if as_binary else SensorInfo(**params)
            settings = Settings(mqtt=self.mqtt_settings, entity=sensor_info)
            sensor = BinarySensor(settings) if as_binary else Sensor(settings)
            self.entities[id] = sensor

        if as_binary:
            sensor.on() if value else sensor.off()
        else:
            sensor.set_state(value)

    def handle_sensor_updates(self, message):
        # Handle the sensors based on the info returned from our tub.
        # Sensors & Binary Sensors can be combined - use a `type` field.
        # Buttons must be done separately.
        # NFI about lights, temp setting and other modes yet
        for item in message.message_configuration:
            ha = item.get('home_assistant')
            binary_sensor = item.get('binary_sensor', False)
            entity_key = item.get('name')
            value = message.parse().get(entity_key)
            if ha is not None and value is not None:
                # Temporarily assume a standard sensor
                self.sensor(entity_key, ha, value, as_binary=binary_sensor)
