from datetime import timedelta
import logging
import os
import secrets
from pathlib import Path

import app.modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _config_value(section, option, default=None):
    value = get_config.get_config_var(section, option, default)
    return default if value is None else value


def _load_secret_key():
    configured_secret = _config_value('main', 'secret_key')
    if configured_secret:
        if len(configured_secret) < 32:
            raise RuntimeError('ROXYWI_SECRET_KEY must contain at least 32 characters')
        return configured_secret

    lib_path = _config_value('main', 'lib_path', '/var/lib/roxy-wi')
    secret_file = Path(_config_value('main', 'secret_key_file', f'{lib_path}/keys/flask-secret'))
    try:
        secret = secret_file.read_text(encoding='utf-8').strip()
        if len(secret) < 32:
            raise RuntimeError(f'{secret_file} must contain at least 32 characters')
        return secret
    except FileNotFoundError:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        generated_secret = secrets.token_urlsafe(48)
        try:
            descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            secret = secret_file.read_text(encoding='utf-8').strip()
            if len(secret) < 32:
                raise RuntimeError(f'{secret_file} must contain at least 32 characters')
            return secret
        with os.fdopen(descriptor, 'w', encoding='utf-8') as secret_stream:
            secret_stream.write(generated_secret)
        return generated_secret


def _load_jwt_configuration():
    algorithm = _config_value('main', 'jwt_algorithm', 'RS256')
    if algorithm not in {'RS256', 'HS256'}:
        raise RuntimeError('ROXYWI_JWT_ALGORITHM must be RS256 or HS256')
    if algorithm == 'HS256':
        return algorithm, None, None

    lib_path = _config_value('main', 'lib_path', '/var/lib/roxy-wi')
    private_key_path = Path(_config_value('main', 'jwt_private_key_file', f'{lib_path}/keys/roxy-wi-key'))
    public_key_path = Path(_config_value('main', 'jwt_public_key_file', f'{lib_path}/keys/roxy-wi-key.pub'))
    return (
        algorithm,
        private_key_path.read_text(encoding='utf-8'),
        public_key_path.read_text(encoding='utf-8'),
    )


_jwt_algorithm, _jwt_private_key, _jwt_public_key = _load_jwt_configuration()


class Configuration(object):
    SECRET_KEY = _load_secret_key()
    TESTING = _as_bool(_config_value('main', 'testing', '0'))
    DEPLOYMENT_MODE = str(_config_value('main', 'deployment_mode', 'package')).lower()
    if DEPLOYMENT_MODE not in {'package', 'compose', 'kubernetes'}:
        raise RuntimeError('ROXYWI_DEPLOYMENT_MODE must be package, compose or kubernetes')
    CACHE_TYPE = str(_config_value(
        'cache',
        'type',
        'NullCache',
    ))
    CACHE_DEFAULT_TIMEOUT = int(_config_value('cache', 'default_timeout', '3000'))
    # The APScheduler HTTP API must never be exposed by Roxy-WI.
    SCHEDULER_API_ENABLED = False
    SCHEDULER_ENABLED = _as_bool(_config_value('main', 'scheduler_enabled', '0'))
    AUTO_MIGRATE = _as_bool(_config_value(
        'main', 'auto_migrate', '1' if DEPLOYMENT_MODE == 'package' else '0'
    ))
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(_config_value('main', 'jwt_expires_hours', '1')))
    JWT_ALGORITHM = _jwt_algorithm
    JWT_PRIVATE_KEY = _jwt_private_key
    JWT_PUBLIC_KEY = _jwt_public_key
    JWT_SECRET_KEY = _config_value('main', 'jwt_secret_key', SECRET_KEY)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_IDENTITY_CLAIM = 'user_id'
    JWT_ERROR_MESSAGE_KEY = 'error'
    JWT_COOKIE_SECURE = True
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_COOKIE_CSRF_PROTECT = True
    SOCKET_TICKET_SECONDS = max(
        30,
        min(900, int(_config_value('main', 'socket_ticket_seconds', '300'))),
    )
    SESSION_COOKIE_SECURE = _as_bool(_config_value('main', 'session_cookie_secure', '1'))
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = True
    # Canonical external URL used for OIDC redirect URIs when Roxy-WI is
    # behind a reverse proxy, for example https://roxy-wi.example.com.
    PUBLIC_URL = str(_config_value('main', 'public_url', '')).rstrip('/')
    MAX_CONTENT_LENGTH = int(_config_value('main', 'max_content_length', str(16 * 1024 * 1024)))
    MAX_FORM_MEMORY_SIZE = int(_config_value('main', 'max_form_memory_size', str(2 * 1024 * 1024)))
    FLASK_PYDANTIC_VALIDATION_ERROR_RAISE = True
    PROXY_FIX_ENABLED = _as_bool(_config_value(
        'proxy', 'enabled', '1' if DEPLOYMENT_MODE != 'package' else '0'
    ))
    PROXY_FIX_X_FOR = int(_config_value('proxy', 'x_for', '1'))
    PROXY_FIX_X_PROTO = int(_config_value('proxy', 'x_proto', '1'))
    PROXY_FIX_X_HOST = int(_config_value('proxy', 'x_host', '1'))
    PROXY_FIX_X_PORT = int(_config_value('proxy', 'x_port', '1'))
    PROXY_FIX_X_PREFIX = int(_config_value('proxy', 'x_prefix', '0'))

    # Logging configuration
    LOG_PATH = _config_value('main', 'log_path', '/var/log/roxy-wi')
    LOG_FILE = str(_config_value('logs', 'log_file', 'roxy-wi.log'))
    LOG_LEVEL = getattr(logging, str(_config_value('logs', 'log_level', 'INFO')).upper(), logging.INFO)
    LOG_CONSOLE = _as_bool(_config_value(
        'logs', 'log_console', '1' if DEPLOYMENT_MODE != 'package' else '0'
    ))
    LOG_FILE_ENABLED = _as_bool(_config_value(
        'logs', 'log_file_enabled', '1' if DEPLOYMENT_MODE == 'package' else '0'
    ))
