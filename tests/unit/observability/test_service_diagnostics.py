import pytest

from app.modules.tools.diagnostics import error_reason, redact_error


@pytest.mark.parametrize('message,reason', [
    ('distributed keepalived checks require a credential provider or a target-side probe agent', 'keepalived'),
    ('Connection refused', 'refused'), ('ReadTimeout', 'timeout'),
    ('NameResolutionError', 'dns'), ('401 Client Error', 'access'),
    ('ACCESS_REFUSED', 'access'), ('SSLError', 'tls'), ('unexpected error', 'unknown_error'),
])
def test_actionable_error_classification(message, reason):
    assert error_reason(message) == reason


@pytest.mark.parametrize('message,secret', [
    ('amqp://user:p4ss@broker:5672/vhost', 'p4ss'),
    ('https://host/path?api_key=private#private', 'private'),
    ('password="private with spaces"', 'private with spaces'),
    ("{'token': 'private value'}", 'private value'),
    ('Authorization: Bearer private-token', 'private-token'),
    ('authorization=Basic c2VjcmV0', 'c2VjcmV0'),
    ('-----BEGIN RSA PRIVATE KEY-----\nsecret-data\n-----END RSA PRIVATE KEY-----', 'secret-data'),
])
def test_error_details_do_not_expose_credentials(message, secret):
    assert secret not in redact_error(message)
