import asyncio
import logging
import sys
from datetime import datetime
from enum import Enum
from logging import Logger

from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo, BinarySensorInfo, BinarySensor, LightInfo, Light, \
    ButtonInfo, Button, NumberInfo, Number
from paho.mqtt.client import MQTTMessage, Client

from spa2mqtt.spas.base.spa import Spa


class EntityType(Enum):
    BUTTON = 'button'
    LIGHT = 'light'
    SENSOR = 'sensor'
    BINARY_SENSOR = 'binary_sensor'
    NUMBER = 'number'


class MQTTControl:
    sensor_updated_at = {}
    default_interval: int
    interval_overrides: dict
    last_values: dict = {}
    last_changed: dict = {}
    entities = {}  # Persistence
    spa: Spa = None

    def __init__(self, sensor_update_intervals: dict = {}, logger: Logger = None, broker_host='localhost',
                 broker_port=1883, device='Jacuzzi J235',
                 device_id='185569045'):
        self.sensor_update_intervals = sensor_update_intervals
        self.mqtt_settings = Settings.MQTT(host=broker_host, port=broker_port)
        self.device_name = device
        self.device_id = device_id
        self.logger = logger or logging.getLogger(self.device_name)
        self.default_interval = sensor_update_intervals.get('default', 15)
        self.interval_overrides = sensor_update_intervals.get('overrides', {})

    def attach_spa(self, spa: Spa):
        self.spa = spa

    def get_device_info(self) -> DeviceInfo:
        # Define the device. At least one of `identifiers` or `connections` must be supplied
        return DeviceInfo(
            name=self.device_name,
            identifiers=self.device_id,
            manufacturer=self.device_name,
            model=self.device_id,
        )

    def button_callback(self, client, userdata, message):
        if self.spa is None:
            raise Exception('No spa has been attached.')

        method_name = userdata['method']

        method = getattr(self.spa, method_name)

        # print(method)
        asyncio.run(method(**userdata['args']))

    def number_callback(self, client, userdata, message):
        print(userdata, )

        method_name = userdata['method']

        method = getattr(self.spa, method_name)

        # print(method)
        asyncio.run(method(message.payload.decode()))

    def light_callback(self, client: Client, user_data, message: MQTTMessage):
        pass

    def sensor(self, entity_key, sensor_config, value, as_binary=False):
        if entity_key in self.entities:
            sensor = self.entities[entity_key]
        else:
            params = {**sensor_config, **{'device': self.get_device_info()}, 'unique_id': entity_key}
            sensor_info = BinarySensorInfo(**params) if as_binary else SensorInfo(**params)
            settings = Settings(mqtt=self.mqtt_settings, entity=sensor_info)
            sensor = BinarySensor(settings) if as_binary else Sensor(settings)
            self.entities[entity_key] = sensor

        if not self.sensor_can_update(entity_key, value):
            return

        if as_binary:
            sensor.on() if value else sensor.off()
        else:
            sensor.set_state(value)

        print(entity_key, value)
        self.sensor_updated_at[entity_key] = datetime.now().timestamp()
        self.last_values[entity_key] = value
        self.last_changed[entity_key] = datetime.now()

    def number(self, entity_key: str, number_config: dict, action_config: dict, value_config: dict):
        refresh = False

        if entity_key in self.entities:
            number = self.entities[entity_key]
            refresh = True
        else:
            params = {**number_config, **{'device': self.get_device_info()}, 'unique_id': entity_key}
            number_info = NumberInfo(**params)
            settings = Settings(mqtt=self.mqtt_settings, entity=number_info)
            number = Number(settings=settings, user_data=action_config, command_callback=self.number_callback)

            number.write_config()
            self.entities[entity_key] = number

        if "from" not in value_config:
            return

        from_key = value_config["from"]
        value = self.last_values[from_key]
        stability_period = value_config.get("stability_period", 1)

        current_ts = datetime.now()
        stability_age = current_ts.timestamp() - self.last_changed.get(from_key, current_ts).timestamp()

        if refresh and stability_age < stability_period:
            return

        if not self.sensor_can_update(entity_key, value):
            return

        number.set_value(value)
        self.sensor_updated_at[entity_key] = current_ts.timestamp() # Why do i duplicate this?
        self.last_values[entity_key] = value
        self.last_changed[entity_key] = current_ts

    def button(self, entity_key: str, button_config: dict, action_config: dict):
        if entity_key in self.entities:
            return
        params = {**button_config, **{'device': self.get_device_info()}, 'unique_id': entity_key}
        button_info = ButtonInfo(**params)
        settings = Settings(mqtt=self.mqtt_settings, entity=button_info)
        button = Button(settings=settings, user_data=action_config, command_callback=self.button_callback)

        button.write_config()
        self.entities[entity_key] = button

        # # Define an optional object to be passed back to the callback
        # user_data = "Some custom data"
        #
        # # Instantiate the button
        # my_button = Button(settings, my_callback, user_data)
        #
        # # Publish the button's discoverability message to let HA automatically notice it
        # my_button.write_config()

    def sensor_can_update(self, sensor_id, value):
        if sensor_id not in self.sensor_updated_at:
            return True


        if self.last_values.get(sensor_id, None) != value:
            return True

        interval = self.interval_overrides.get(sensor_id, self.default_interval)
        return (datetime.now().timestamp() - self.sensor_updated_at[sensor_id]) >= interval

    def handle_sensor_updates(self, message):
        # Handle the sensors based on the info returned from our tub.
        # Buttons must be done separately.
        # NFI about lights, temp setting and other modes yet
        for item in message.message_configuration:
            entity_type = EntityType(item.get('type', EntityType.SENSOR))
            match entity_type:
                case EntityType.NUMBER:
                    entity_key = item.get('name')
                    ha = item.get('home_assistant', {})
                    self.number(entity_key, ha, item.get('action', {}), item.get('value', {}))
                case EntityType.BUTTON:
                    entity_key = item.get('name')
                    ha = item.get('home_assistant', {})
                    self.button(entity_key, ha, item.get('action', {}))
                case EntityType.SENSOR | EntityType.BINARY_SENSOR:
                    ha = item.get('home_assistant')
                    binary_sensor = (entity_type == EntityType.BINARY_SENSOR)
                    entity_key = item.get('name')

                    value = message.parse().get(entity_key)

                    if ha is not None and value is not None:
                        # Temporarily assume a standard sensor
                        self.sensor(entity_key, ha, value, as_binary=binary_sensor)
                case '_':
                    print('DEFAULT')
