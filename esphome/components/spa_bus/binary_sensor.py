import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor

from . import CONF_ENTITY, CONF_SPA_BUS_ID, SpaBus, entity_schema_validator, hub_definition
from . import definition as defs

DEPENDENCIES = ["spa_bus"]

CONFIG_SCHEMA = binary_sensor.binary_sensor_schema().extend(
    {
        cv.GenerateID(CONF_SPA_BUS_ID): cv.use_id(SpaBus),
        cv.Required(CONF_ENTITY): cv.string_strict,
    }
)
FINAL_VALIDATE_SCHEMA = entity_schema_validator("binary_sensor")


async def to_code(config):
    hub = await cg.get_variable(config[CONF_SPA_BUS_ID])
    sens = await binary_sensor.new_binary_sensor(config)
    defn = hub_definition()
    ent = defs.entity(defn, config[CONF_ENTITY])
    cg.add(hub.register_binary_sensor(defs.field_index(defn, ent["field"]), sens))
