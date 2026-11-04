import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import button

from . import CONF_ENTITY, CONF_SPA_BUS_ID, SpaBus, entity_schema_validator, hub_definition, spa_bus_ns
from . import definition as defs

DEPENDENCIES = ["spa_bus"]

SpaButton = spa_bus_ns.class_("SpaButton", button.Button)

CONFIG_SCHEMA = button.button_schema(SpaButton).extend(
    {
        cv.GenerateID(CONF_SPA_BUS_ID): cv.use_id(SpaBus),
        cv.Required(CONF_ENTITY): cv.string_strict,
    }
)
FINAL_VALIDATE_SCHEMA = entity_schema_validator("button")


async def to_code(config):
    hub = await cg.get_variable(config[CONF_SPA_BUS_ID])
    btn = await button.new_button(config)
    defn = hub_definition()
    ent = defs.entity(defn, config[CONF_ENTITY])
    cg.add(btn.set_parent(hub))
    cg.add(btn.set_code(defs.button_code(defn, ent["press"])))
