import json
from html.parser import HTMLParser

import pytest

from app.modules.service import common


@pytest.mark.parametrize('output,expected', [
    ('node_exporter, version 1.12.0 (branch: HEAD)', '1.12.0'), ('no\n', 'no'),
])
def test_version_route_preserves_text_contract(product_client, monkeypatch, output, expected):
    monkeypatch.setattr(common.server_mod, 'ssh_command', lambda *args, **kwargs: output)
    response = product_client.get('/install/exporter/node/version/192.0.2.11')
    assert response.status_code == 200
    assert response.text == expected


def test_version_route_rejects_unknown_exporter_before_ssh(product_client, monkeypatch):
    calls = []
    monkeypatch.setattr(common.server_mod, 'ssh_command', lambda *args, **kwargs: calls.append(args))
    response = product_client.get('/install/exporter/invalid/version/192.0.2.11')
    assert response.status_code == 400
    assert calls == []


def test_version_route_does_not_return_connection_error_as_version(product_client, monkeypatch):
    def ssh(*args, **kwargs):
        raise TimeoutError('private SSH details')

    monkeypatch.setattr(common.server_mod, 'ssh_command', ssh)
    response = product_client.get('/install/exporter/node/version/192.0.2.11')
    assert response.status_code == 500
    assert 'private SSH details' not in response.text


def test_install_page_supplies_exporter_messages(product_client, monkeypatch):
    monkeypatch.setattr('app.modules.common.common.is_tool', lambda *_: True)

    class Messages(HTMLParser):
        def __init__(self):
            super().__init__()
            self.selected = False
            self.text = ''

        def handle_starttag(self, tag, attrs):
            if tag == 'script':
                self.selected = dict(attrs).get('id') == 'exporter-check-messages'

        def handle_data(self, data):
            if self.selected:
                self.text += data

        def handle_endtag(self, tag):
            if tag == 'script':
                self.selected = False

    response = product_client.get('/install')
    assert response.status_code == 200
    messages = Messages()
    messages.feed(response.text)
    assert json.loads(messages.text)['checking'] == 'Checking exporter installation…'
