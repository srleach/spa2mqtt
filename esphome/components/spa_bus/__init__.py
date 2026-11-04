"""spa_bus: native ESPHome component for Balboa-family "encrypted" hot-tub buses
(Jacuzzi J235 and relatives), driven by spa2mqtt tub definitions.

The tub definition YAML (repo `definitions/`) is read at compile time and turned into
field/button tables in C++. See docs/design.md section 7.
"""

from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome import pins
from esphome.components import text_sensor as text_sensor_component
from esphome.components import uart
from esphome.const import CONF_ID
from esphome.core import CORE
from esphome.cpp_generator import RawStatement

from . import definition as defs

CODEOWNERS = ["@srleach"]
DEPENDENCIES = ["uart"]
AUTO_LOAD = ["text_sensor"]

CONF_SPA_BUS_ID = "spa_bus_id"
CONF_DEFINITION = "definition"
CONF_TRANSMIT = "transmit"
CONF_FLOW_CONTROL_PIN = "flow_control_pin"
CONF_HEARTBEAT = "heartbeat"
CONF_BUS_STATE = "bus_state"
CONF_ENTITY = "entity"

spa_bus_ns = cg.esphome_ns.namespace("spa_bus")
SpaBus = spa_bus_ns.class_("SpaBus", cg.Component, uart.UARTDevice)


def _definition_ref(value):
    value = cv.string_strict(value)
    ref = value
    if value.endswith((".yaml", ".yml")):
        ref = str(Path(CORE.relative_config_path(value)))
    try:
        defs.load(ref)
    except defs.DefinitionError as exc:
        raise cv.Invalid(str(exc)) from exc
    return ref


CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SpaBus),
            cv.Required(CONF_DEFINITION): _definition_ref,
            # SAFETY: false = receive-only. Buttons/number log and do nothing.
            cv.Optional(CONF_TRANSMIT, default=False): cv.boolean,
            cv.Optional(CONF_FLOW_CONTROL_PIN): pins.gpio_output_pin_schema,
            cv.Optional(CONF_HEARTBEAT, default="60s"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_BUS_STATE): text_sensor_component.text_sensor_schema(
                entity_category="diagnostic", icon="mdi:transit-connection-variant"
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)


def _final_validate(config):
    defn = defs.load(config[CONF_DEFINITION])
    baud = defn.get("bus", {}).get("baud", 115200)
    return uart.final_validate_device_schema(
        "spa_bus", baud_rate=baud, require_rx=True, require_tx=config[CONF_TRANSMIT]
    )(config)


FINAL_VALIDATE_SCHEMA = _final_validate


def hub_definition(full_config=None):
    """Definition of the (single) spa_bus hub, for platform validation and codegen."""
    conf = (full_config or CORE.config)["spa_bus"]
    return defs.load(conf[CONF_DEFINITION])


def entity_schema_validator(component):
    """FINAL_VALIDATE_SCHEMA for platforms: the entity key must exist with this component."""

    def validate(config):
        defn = hub_definition(fv.full_config.get())
        try:
            ent = defs.entity(defn, config[CONF_ENTITY])
        except defs.DefinitionError as exc:
            raise cv.Invalid(str(exc), path=[CONF_ENTITY]) from exc
        if ent["component"] != component:
            raise cv.Invalid(
                f"entity {ent['key']!r} is a {ent['component']} in {defn['id']}, not a {component}",
                path=[CONF_ENTITY],
            )
        return config

    return validate


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    defn = defs.load(config[CONF_DEFINITION])
    for line in defs.cpp_setup_lines(defn, var=str(var)):
        cg.add(RawStatement(line))
    cg.add(var.set_transmit(config[CONF_TRANSMIT]))
    cg.add(var.set_heartbeat(config[CONF_HEARTBEAT]))
    cg.add(var.set_expected_baud(defn.get("bus", {}).get("baud", 115200)))
    if CONF_FLOW_CONTROL_PIN in config:
        pin = await cg.gpio_pin_expression(config[CONF_FLOW_CONTROL_PIN])
        cg.add(var.set_flow_control_pin(pin))
    if CONF_BUS_STATE in config:
        sens = await text_sensor_component.new_text_sensor(config[CONF_BUS_STATE])
        cg.add(var.set_bus_state_sensor(sens))
