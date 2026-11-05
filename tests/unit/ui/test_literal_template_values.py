"""Keep legacy form presentation compatible without weakening HTML escaping."""

from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from flask import g, render_template

from app.modules.roxywi.class_models import BackupRequest, ChannelRequest


pytestmark = pytest.mark.security
LABEL = '''O'Brien's "quoted" <img src=x onerror="alert(1)"> & <svg onload="alert(2)">'''
DISPLAY_LABEL = '''OBriens "quoted" <img src=x onerror="alert(1)"> & <svg onload="alert(2)">'''


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def value(self, element_id):
        return next(attrs['value'] for tag, attrs in self.elements if attrs.get('id') == element_id)

    def assert_no_payload_elements(self):
        assert not any(tag in ('img', 'svg') or 'onerror' in attrs or 'onload' in attrs
                       for tag, attrs in self.elements)


def test_channel_names_are_html_escaped(app):
    channel = SimpleNamespace(id=7, group_id=1, token='synthetic', chanel_name=LABEL)
    with app.test_request_context('/'):
        g.user_params = {'role': 2}
        parsed = Elements(render_template('ajax/channels.html', lang='en', user_params={'role': 2},
                                          groups=[], telegrams=[channel], slacks=[channel],
                                          pds=[channel], mms=[channel]))
    for receiver in ('telegram', 'slack', 'pd', 'mm'):
        assert parsed.value(f'{receiver}-chanel-7') == DISPLAY_LABEL
    parsed.assert_no_payload_elements()


def test_backup_description_cannot_create_elements(app):
    backup = SimpleNamespace(id=7, server_id=1, rserver='backup.test', rpath='/backup',
                             type='backup', time='daily', cred_id=1, description=LABEL)
    with app.test_request_context('/'):
        g.user_params = {'role': 2}
        parsed = Elements(render_template('ajax/new_backup.html', lang='en', backups=[backup],
                                          servers=[(1, 'test', '192.0.2.1')], sshs=[]))
    assert parsed.value('backup-description-7') == DISPLAY_LABEL
    parsed.assert_no_payload_elements()


def test_ha_hostnames_remain_text_in_both_lists(app):
    slave = [None] * 33
    slave[0:3] = [7, LABEL, '192.0.2.7']
    slave[31:33] = [False, 'eth0']
    free = SimpleNamespace(server_id=8, hostname=LABEL, desc=LABEL, ip='192.0.2.8')
    with app.test_request_context('/'):
        parsed = Elements(render_template('ajax/ha/slave_servers.html', lang='en',
                                          slaves=[slave], free_servers=[free]))
    assert parsed.text.count(DISPLAY_LABEL) == 2
    assert [attrs['data-name'] for tag, attrs in parsed.elements if 'data-name' in attrs] == [LABEL, LABEL]
    parsed.assert_no_payload_elements()


def test_channel_form_resave_preserves_existing_storage(app):
    body = ChannelRequest(token='synthetic', channel='daily alerts')
    channel = SimpleNamespace(id=7, group_id=1, token=body.token, chanel_name=body.channel)
    with app.test_request_context('/'):
        g.user_params = {'role': 2}
        parsed = Elements(render_template('ajax/channels.html', lang='en', user_params=g.user_params,
                                          groups=[], telegrams=[channel], slacks=[channel],
                                          pds=[channel], mms=[channel]))
    for receiver in ('telegram', 'slack', 'pd', 'mm'):
        displayed = parsed.value(f'{receiver}-chanel-7')
        assert displayed == 'daily alerts'
        assert ChannelRequest(token='synthetic', channel=displayed).channel == body.channel


def test_backup_form_resave_preserves_existing_storage(app):
    body = BackupRequest(cred_id=1, server_id=1, description='daily backup')
    backup = SimpleNamespace(id=7, server_id=1, rserver='backup.test', rpath='/backup',
                             type='backup', time='daily', cred_id=1, description=body.description)
    with app.test_request_context('/'):
        g.user_params = {'role': 2}
        parsed = Elements(render_template('ajax/new_backup.html', lang='en', backups=[backup],
                                          servers=[(1, 'test', '192.0.2.1')], sshs=[]))
    displayed = parsed.value('backup-description-7')
    assert displayed == 'daily backup'
    assert BackupRequest(cred_id=1, server_id=1, description=displayed).description == body.description
