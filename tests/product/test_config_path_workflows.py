import json
import re
from html import unescape
from pathlib import Path

import pytest

from app.modules.config import config
from app.modules.config.path_tokens import encode_file_path
from app.modules.db.db_model import Setting


@pytest.mark.parametrize('service,root', [('haproxy', '/etc/haproxy'), ('nginx', '/etc/nginx'),
                                        ('apache', '/etc/apache2'), ('keepalived', '/etc/keepalived')])
def test_config_paths_in_templates_and_api_are_lossless(product_client, product, monkeypatch, service, root):
    setattr(product.server, service, 1)
    product.server.save()
    path = root + '/site92.conf' if service != 'haproxy' else root + '/site92.cfg'
    token = encode_file_path(path)
    Setting.update(value=path).where(Setting.param == service + '_config_path', Setting.group_id == 1).execute()
    calls = []
    def download(server, local, **kwargs):
        calls.append(kwargs.get('config_file_name'))
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text('# sample\n', encoding='utf-8')
    monkeypatch.setattr(config, 'get_config', download)
    monkeypatch.setattr(config.server_mod, 'get_remote_files', lambda *a: path + '\x00')

    response = product_client.post(f'/config/{service}/show', json={
        'serv': product.server.ip, 'config_file_name': token})
    assert response.status_code == 200, response.text
    html = response.json['data']
    doc = json.loads(re.search(r'class="cv-document">(.*?)</script>', html, re.S)[1])
    assert doc['source']['path'] == path and doc['source']['file_token'] == token
    if service == 'nginx':
        assert 'data-nginx-edit="site92"' in html
    response = product_client.get(doc['edit_url'])
    assert response.status_code == 200, response.text
    assert f'value="{path}" name="file_path"' in unescape(response.text)
    response = product_client.post(f'/config/{service}/show-files', data={
        'serv': product.server.ip, 'config_file_name': token, 'edit_mode': '1'})
    if service == 'haproxy':
        assert f'id="editor_config_file_name" value="{token}"' in response.text
        assert '<select' not in response.text
    else:
        assert f'value="{token}" selected' in response.text

    # JSON clients send paths directly; the API must not replace literal 92.
    response = product_client.get(f'/api/service/{service}/11/config', query_string={'file_path': path})
    assert response.status_code == 200, response.text
    assert calls[-1] == path
    for action in ('show', 'edit'):
        response = product_client.get(f'/config/{service}/{product.server.ip}/{action}/92etc92{service}92old.conf')
        assert response.status_code == 400, response.text


def test_settings_json_values_are_not_decoded_as_url_paths(product_client, product):
    for parameter, value in [('nginx_config_path', '/etc/nginx/site92.conf'), ('nginx_stats_port', '9200')]:
        response = product_client.post('/admin/settings/nginx', json={'param': parameter, 'value': value})
        assert response.status_code == 201, response.text
        assert Setting.get(Setting.param == parameter, Setting.group_id == 1).value == value
