"""Compose optional credential providers through one public JWT callback."""
import importlib
import importlib.util


SECURITY_PROOF_FIELDS = ('auth_epoch', 'credential_version', 'auth_method', 'auth_time', 'auth_account')


def _optional(name):
    parent = name.rsplit('.', 1)[0]
    if importlib.util.find_spec(parent) is None or importlib.util.find_spec(name) is None:
        return None
    # An installed provider that fails to import must never fail open.
    return importlib.import_module(name)


def verify(payload):
    kind = payload.get('credential_type')
    if kind == 'pat':
        provider = _optional('app.modules.api_tokens.service')
        return provider is not None and bool(provider.verify(payload))
    if kind not in (None, 'session'):
        return False
    provider = _optional('app.modules.authentication.security')
    if provider is not None:
        return bool(provider.validate_session(payload))
    # Removing local-security code cannot turn a factor-bound JWT into an
    # unrestricted legacy session. A complete rollback requires signing in again.
    return not any(field in payload for field in SECURITY_PROOF_FIELDS)
