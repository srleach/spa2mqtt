import yaml


def get_application_configuration(file: str = 'config.yml'):
    with open(file, 'r') as f:
        return yaml.safe_load(f)
    #TODO handle failure


def get_variant_configuration(file: str = 'base'):
    with open(f"spa2mqtt/spa_definitions/{file}.yml", 'r') as f:
        return yaml.safe_load(f)
    #TODO handle failure