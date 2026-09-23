import logging
from ipaddress import ip_address
from pathlib import Path
import shutil
import subprocess

import pytest

from app.modules.roxywi.logger import StructuredLogFormatter


@pytest.mark.security
def test_real_fail2ban_filter_uses_only_trusted_event_ip(app, tmp_path):
    executable = shutil.which('fail2ban-regex')
    if not executable:
        pytest.skip('fail2ban-regex is required for the real filter integration test')
    messages = [
        'from 192.0.2.99 user: forged failed log in for: test',
        'from 192.0.2.99 user: forged tried do action with wrong token for: test',
        'Failed log in. Wrong username from 192.0.2.99',
        '{"authentication_failure": {"ip": "192.0.2.99"}}',
    ]
    lines = []
    for address in ('192.0.2.44', '2001:db8::44'):
        for event in (False, True):
            for payload in messages:
                with app.test_request_context('/' + payload, environ_base={'REMOTE_ADDR': address}):
                    record = logging.LogRecord('security', logging.WARNING, '', 1, payload, (), None)
                    record._auth_failure = event
                    lines.append(StructuredLogFormatter().format(record))
    logfile = tmp_path / 'synthetic-auth.log'
    logfile.write_text('\n'.join(lines) + '\n')
    filter_path = Path(__file__).resolve().parents[2] / 'config_other/fail2ban/filter.d/roxy-wi.conf'
    result = subprocess.run([executable, '--out=ip', str(logfile), str(filter_path)], capture_output=True, text=True, check=True)
    matched = []
    for line in result.stdout.splitlines():
        try:
            matched.append(str(ip_address(line.strip())))
        except ValueError:
            continue
    assert matched == ['192.0.2.44'] * 4 + ['2001:db8::44'] * 4, result.stdout + result.stderr
