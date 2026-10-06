"""Lossless URL tokens for configuration paths, shared by all services."""
import base64
import binascii


def encode_file_path(path: str) -> str:
    return '_p_' + base64.urlsafe_b64encode(path.encode('utf-8')).decode('ascii').rstrip('=')


def decode_file_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Invalid configuration file path')
    if value.startswith('/'):
        return value
    if value.startswith('_p_'):
        try:
            token = value[3:]
            path = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True).decode('utf-8')
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError('Invalid configuration file token') from exc
        if path.startswith('/'):
            return path
    raise ValueError('Expected an absolute configuration path or a _p_ file token')
