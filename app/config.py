from datetime import timedelta
import logging

import app.modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()


class Configuration(object):
    SECRET_KEY = 'very secret salt to protect your Roxy-WI sessions'
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 3000
    SCHEDULER_API_ENABLED = True
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)
    JWT_ALGORITHM = 'RS256'
    JWT_PRIVATE_KEY = open('/var/lib/roxy-wi/keys/roxy-wi-key').read()
    JWT_PUBLIC_KEY = open('/var/lib/roxy-wi/keys/roxy-wi-key.pub').read()
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_IDENTITY_CLAIM = 'user_id'
    JWT_ERROR_MESSAGE_KEY = 'error'
    FLASK_PYDANTIC_VALIDATION_ERROR_RAISE = True

    # Logging configuration
    LOG_PATH = get_config.get_config_var('main', 'log_path')
    LOG_FILE = 'roxy-wi.log'
    LOG_LEVEL = logging.INFO
    LOG_CONSOLE = False  # Set to True to also log to console
