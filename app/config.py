from datetime import timedelta


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
