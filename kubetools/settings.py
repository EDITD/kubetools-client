from os import access, listdir, path, X_OK

import click

from pydash import memoize
from six.moves.configparser import ConfigParser

from .log import logger


class KubetoolsSettings(object):
    KUBETOOLS_HOST = None
    KUBETOOLS_PORT = 80
    KUBETOOLS_API_VERSION = 4

    DEFAULT_KUBE_ENV = 'staging'  # default environment when speaking to the server

    DEV_DEFAULT_ENV = 'dev'  # default environment name in dev
    DEV_HOST = 'localhost'  # dev host to link people to (should map to 127.0.0.1)
    DEV_CONFIG_DIRNAME = '.kubetools'  # project directroy to generate compose config
    DEV_BACKEND = 'docker_compose'  # backend to use for development

    KUBETOOLS_SESSION = None  # user auth/session details (generated by the server)

    WAIT_SLEEP_TIME = 3
    WAIT_MAX_SLEEPS = 300 / WAIT_SLEEP_TIME

    def __init__(self, debug=False, filename=None):
        self.debug = debug
        self.filename = filename
        self.scripts = []


def get_settings_directory():
    return click.get_app_dir('kubetools', force_posix=True)


def _get_settings(debug=False):
    settings_directory = get_settings_directory()
    settings_file = path.join(settings_directory, 'kubetools.conf')

    settings = KubetoolsSettings(debug=debug, filename=settings_file)

    if path.exists(settings_file):
        logger.info('Loading settings file: {0}'.format(settings_file))
        parser = ConfigParser()
        parser.read(settings_file)

        for option in parser.options('kubetools'):
            setattr(
                settings,
                option.upper().replace('-', '_'),
                parser.get('kubetools', option),
            )

    else:
        logger.info('No settings file: {0}'.format(settings_file))

    scripts_directory = path.join(settings_directory, 'scripts')
    if path.exists(scripts_directory):
        for filename in listdir(scripts_directory):
            if access(path.join(scripts_directory, filename), X_OK):
                settings.scripts.append(filename)

    return settings


get_settings = memoize(
    _get_settings,
    # Ensure we always memoize even if not always called with the same args
    # this is because we initially bootstrap the settings at the CLI entry points
    # with the debug kwarg, but in sub-CLI functions we don't have the original
    # debug arg, but rely on the cached settings.
    resolver=lambda *args, **kwargs: 'settings',
)