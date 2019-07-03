import os
import yaml
import logging
from snsync.exceptions import ConfigurationFileNotFound, InvalidConfiguration

logger = logging.getLogger(__name__)

INSTANCE_DEFAULT_CONFIG = {
    'read_only': False,
    'verify_ssl': True
}

INSTANCE_REQUIRED_FIELDS = [
    'host',
]

RECORD_REQUIRED_FIELDS = [
    'table',
    'key',
    'fields'
]


def find_config_file(file_name):
    """ Searches for a configuration file
        This searches for configuration files in the current directory and every directory above it
        If no configuration file is found raises an error
    """

    cur_dir = os.getcwd()

    while True:
        file_list = os.listdir(cur_dir)
        parent_dir = os.path.dirname(cur_dir)
        if file_name in file_list:
            return os.path.join(cur_dir, file_name)
        # If we are at the root directory
        elif cur_dir == parent_dir:
            raise ConfigurationFileNotFound(
                "Not a sn-sync repository (or any parent up to root)\n"
                "Could not locate configuration file: {}".format(file_name))
        else:
            cur_dir = parent_dir


def merge_defaults(config, defaults):
    """ Merge a configuration dict with a dict of defaults """

    for key, value in defaults.items():
        if key in config:
            continue
        config[key] = value


class SNConfig(object):

    def __init__(self, config_file_name='snconfig.yaml'):

        config_file = find_config_file(config_file_name)

        logger.debug('Loading configuration file: {}'.format(config_file))

        # Load the configuration
        with open(config_file, 'r') as stream:
            try:
                self._config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise InvalidConfiguration(
                    'Unable to parse YAML file {}. Error: {}'
                    ''.format(config_path, e)
                ) from exc

        self._config['config_file'] = config_file
        self._config['root_dir'] = os.path.dirname(config_file)

        logger.debug('Repository root set to {}'.format(self._config['root_dir']))

        # Check and set defaults for instances
        for name, instance in self._config['instances'].items():
            if not all(key in instance.keys() for key in INSTANCE_REQUIRED_FIELDS):
                raise InvalidConfiguration(
                    'Instance {} missing required fields: {}'.format(
                        name, ','.join(INSTANCE_REQUIRED_FIELDS)))

            # Check for default
            if instance.get('default', False):
                if 'default_instance' in self._config:
                    logger.warn('Default instance already set to {}. Overwriting to {}'.format(
                        self._config['default_instance'], name))
                self._config['default_instance'] = name

            # Merge in defaults
            merge_defaults(instance, INSTANCE_DEFAULT_CONFIG)

        # Get the default instance, if not already set
        if 'default_instance' not in self._config:
            inst = list(self._config['instances'].keys())[0]
            self._config['default_instance'] = inst

        logger.debug("Default service now instance: {}".format(self._config['default_instance']))

        # Load and check the record options
        for name, record in self._config['records'].items():
            if not all(key in record.keys() for key in RECORD_REQUIRED_FIELDS):
                raise InvalidConfiguration(
                    'Record {} missing required fields: {}'.format(
                        name, ','.join(RECORD_REQUIRED_FIELDS)))


    def __getattr__(self, name):
        return self._config[name]

    def get_record_config(self, record):
        return self._config['records'].get(record)
