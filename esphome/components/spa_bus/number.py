import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import number

from . import CONF_ENTITY, CONF_SPA_BUS_ID, SpaBus, entity_schema_validator, hub_definition, spa_bus_ns
from . import definition as defs

DEPENDENCIES = ["spa_bus"]

SpaNumber = spa_bus_ns.class_("SpaNumber", number.Number)

CONFIG_SCHEMA = number.number_schema(SpaNumber).extend(
    {
        cv.GenerateID(CONF_SPA_BUS_ID): cv.use_id(SpaBus),
        cv.Required(CONF_ENTITY): cv.string_strict,
    }
)
FINAL_VALIDATE_SCHEMA = entity_schema_validator("number")


async def to_code(config):
    hub = await cg.get_variable(config[CONF_SPA_BUS_ID])
    defn = hub_definition()
    ent = defs.entity(defn, config[CONF_ENTITY])
    ctl = ent["control"]
    num = await number.new_number(config, min_value=ent["min"], max_value=ent["max"], step=ent["step"])
    cg.add(
        hub.register_setpoint(
            num,
            defs.field_index(defn, ent["field"]),
            defs.button_code(defn, ctl["up"]),
            defs.button_code(defn, ctl["down"]),
            ent["step"],
            ent["min"],
            ent["max"],
            ctl.get("confirm_frames", 3),
            ctl.get("max_attempts", 40),
        )
    )
