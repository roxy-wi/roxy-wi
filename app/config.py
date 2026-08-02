from datetime import timedelta
import logging
import os
import secrets
from pathlib import Path

import app.modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()


def _load_secret_key():
    configured_secret = os.environ.get('ROXYWI_SECRET_KEY')
    if configured_secret:
        if len(configured_secret) < 32:
            raise RuntimeError('ROXYWI_SECRET_KEY must contain at least 32 characters')
        return configured_secret

    secret_file = Path(os.environ.get('ROXYWI_SECRET_KEY_FILE', '/var/lib/roxy-wi/keys/flask-secret'))
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
    algorithm = os.environ.get('ROXYWI_JWT_ALGORITHM', 'RS256')
    if algorithm not in {'RS256', 'HS256'}:
        raise RuntimeError('ROXYWI_JWT_ALGORITHM must be RS256 or HS256')
    if algorithm == 'HS256':
        return algorithm, None, None

    private_key_path = Path(os.environ.get('ROXYWI_JWT_PRIVATE_KEY_FILE', '/var/lib/roxy-wi/keys/roxy-wi-key'))
    public_key_path = Path(os.environ.get('ROXYWI_JWT_PUBLIC_KEY_FILE', '/var/lib/roxy-wi/keys/roxy-wi-key.pub'))
    return (
        algorithm,
        private_key_path.read_text(encoding='utf-8'),
        public_key_path.read_text(encoding='utf-8'),
    )


_jwt_algorithm, _jwt_private_key, _jwt_public_key = _load_jwt_configuration()


class Configuration(object):
    SECRET_KEY = _load_secret_key()
    TESTING = os.environ.get('ROXYWI_TESTING') == '1'
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 3000
    # The APScheduler HTTP API must never be exposed by Roxy-WI.
    SCHEDULER_API_ENABLED = False
    SCHEDULER_ENABLED = os.environ.get('ROXYWI_SCHEDULER_ENABLED') == '1'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('ROXYWI_JWT_EXPIRES_HOURS', '1')))
    JWT_ALGORITHM = _jwt_algorithm
    JWT_PRIVATE_KEY = _jwt_private_key
    JWT_PUBLIC_KEY = _jwt_public_key
    JWT_SECRET_KEY = os.environ.get('ROXYWI_JWT_SECRET_KEY', SECRET_KEY)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_IDENTITY_CLAIM = 'user_id'
    JWT_ERROR_MESSAGE_KEY = 'error'
    JWT_COOKIE_SECURE = True
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_COOKIE_CSRF_PROTECT = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = True
    MAX_CONTENT_LENGTH = int(os.environ.get('ROXYWI_MAX_CONTENT_LENGTH', str(16 * 1024 * 1024)))
    MAX_FORM_MEMORY_SIZE = int(os.environ.get('ROXYWI_MAX_FORM_MEMORY_SIZE', str(2 * 1024 * 1024)))
    FLASK_PYDANTIC_VALIDATION_ERROR_RAISE = True

    # Logging configuration
    LOG_PATH = os.environ.get('ROXYWI_LOG_PATH', get_config.get_config_var('main', 'log_path'))
    LOG_FILE = 'roxy-wi.log'
    LOG_LEVEL = logging.INFO
    LOG_CONSOLE = False  # Set to True to also log to console
