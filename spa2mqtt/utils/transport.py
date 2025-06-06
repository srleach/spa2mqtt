import importlib
import logging

from spa2mqtt.spas.base.communicator import Communicator

logger = logging.getLogger(__name__)


def load_class(module_name: str, class_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def make_tub(family: str, spa_variant: str, args):  # TODO: Hint Return Type...
    return load_class(f"spa2mqtt.spas.{family}.spa", spa_variant)(**args)


def make_communicator(family: str, communicator: str, args) -> Communicator:
    return load_class(f"spa2mqtt.spas.{family}.communicator", communicator)(**args)


def get_communicator(spa_configuration: dict, variant_configuration: dict) -> Communicator:
    """
    Build the communicator for SPAs.
    :return:
    """
    return make_communicator(
        variant_configuration.get('family'),
        variant_configuration.get('communicator'),
        spa_configuration.get('connection')
    )
