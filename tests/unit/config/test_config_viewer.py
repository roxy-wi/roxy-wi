import json
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from flask import g, render_template
import pytest

from app.modules.config import config as config_mod, common, section
from app.modules.config.viewer import build_document, haproxy_sections, source_lines
from app.modules.config.path_tokens import encode_file_path


def document(text, **kwargs):
    values = dict(service='haproxy', server='192.0.2.11', file_path='/etc/haproxy/haproxy.cfg', editable=True, main_file=True)
    values.update(kwargs)
    return build_document(text, **values)


def test_source_is_lossless_and_sections_partition_all_lines():
    text = '# preamble\r\n\r\nglobal\r\n\tdaemon\r\n\r\n# BEGIN Roxy-WI MANAGED backend web do not edit it directly\r\nbackend web\r\n  server a 192.0.2.1:80\r\n# END Roxy-WI MANAGED backend web do not edit it directly\r\nbackend last'
    doc = document(text)
    assert doc['text'] == text
    assert doc['line_count'] == 10
    lines = source_lines(text)
    assert ''.join(''.join(lines[item['start_line'] - 1:item['end_line']]) for item in doc['sections']) == text
    assert [(item['kind'], item['start_line'], item['header_line'], item['end_line']) for item in doc['sections']] == [
        ('preamble', 1, 1, 2), ('global', 3, 3, 5), ('backend', 6, 7, 9), ('backend', 10, 10, 10),
    ]


def test_section_keywords_are_tokens_not_directive_prefixes():
    sections = haproxy_sections('global\n  log-forwarded value\n  frontend-name value\n  # backend comment\nbackend\tweb\n')
    assert [item['kind'] for item in sections] == ['global', 'backend']


def test_section_editing_preserves_both_form_and_text_paths():
    doc = document('global\n daemon\nbackend web\n server one :80\nresolvers dns\n nameserver local :53\n')
    assert [item['editor'] for item in doc['sections']] == ['form-or-text', 'form-or-text', 'text']
    web = doc['sections'][1]
    assert parse_qs(urlsplit(web['edit_url']).query) == {
        'file_path': ['/etc/haproxy/haproxy.cfg'], 'section_line': ['3'],
    }
    assert web['stats_url'].endswith('#web')


def test_file_identity_supports_forms_and_duplicate_names_require_text():
    source = 'backend web\n server one :80\n'
    main = document(source)['sections'][0]
    other = document(source, file_path='/etc/haproxy/conf.d/extra.cfg', main_file=False)['sections'][0]
    assert other['id'] != main['id']
    assert other['editor'] == 'form-or-text'
    assert parse_qs(urlsplit(other['edit_url']).query)['file_path'] == ['/etc/haproxy/conf.d/extra.cfg']
    repeated = document(source + source)['sections']
    assert all(item['editor'] == 'text' for item in repeated)
    assert len({item['id'] for item in repeated}) == 2


@pytest.mark.parametrize('kwargs', [dict(version='saved.cfg'), dict(editable=False)])
def test_readonly_source_has_no_edit_actions(kwargs):
    doc = document('frontend web\n bind :80\n', **kwargs)
    assert doc['edit_url'] is None
    assert doc['sections'][0]['edit_url'] is None
    assert doc['sections'][0]['editor'] is None


@pytest.mark.parametrize('service,text,titles', [
    ('nginx', '# heading\nworker_processes auto;\nevents {\n worker_connections 1024;\n}\nhttp {\n server {\n location ~ ^/x{1,3}$ {\n return 200 "} # not a comment";\n }\n }\n}\nstream {\n}\n', ['events {', 'http {', 'stream {']),
    ('keepalived', 'global_defs {\n router_id LB\n}\nvrrp_instance VI_1 {\n virtual_ipaddress {\n 192.0.2.10\n }\n}\n', ['global_defs {', 'vrrp_instance VI_1 {']),
    ('apache', 'Listen 80\n<VirtualHost *:80>\n ServerName a.test\n</VirtualHost>\n<VirtualHost *:443>\n</VirtualHost>\n', ['<VirtualHost *:80>', '<VirtualHost *:443>']),
])
def test_other_services_preserve_nested_blocks_and_source(service, text, titles):
    doc = document(text, service=service)
    assert [item['title'] for item in doc['sections'] if item['kind'] != 'preamble'] == titles
    assert doc['text'] == text


def test_empty_file_is_a_valid_document():
    doc = document('')
    assert doc['sections'] == []
    assert doc['line_count'] == 0


def test_listener_links_handle_ssl_multiple_binds_and_non_tcp_addresses():
    source = 'frontend web\n bind :80\n bind [::]:443,127.0.0.1:8443 ssl crt /tmp/a.pem\n bind unix@/tmp/app.sock\n bind :8000-8010\n bind :99999\n'
    links = document(source, server='2001:db8::1')['sections'][0]['open_urls']
    assert [link['url'] for link in links] == ['http://[2001:db8::1]:80/', 'https://[2001:db8::1]:443/', 'https://[2001:db8::1]:8443/']
    assert document(source, version='saved.cfg')['sections'][0]['open_urls'] == []


def test_text_editor_replaces_one_line_section_without_deleting_next(tmp_path):
    path = tmp_path / 'haproxy.cfg'
    path.write_text('global\ndefaults\n timeout connect 5s\nbackend web', encoding='utf-8', newline='')
    start, end, text = section.get_section_from_config(str(path), 'global')
    assert (start, end, text) == (0, 0, 'global\n')
    assert section.rewrite_section(start, end, str(path), 'global\n daemon') == 'global\n daemon\ndefaults\n timeout connect 5s\nbackend web'
    assert section.rewrite_section(start, end, str(path), '') == 'defaults\n timeout connect 5s\nbackend web'
    start, end, text = section.get_section_from_config(str(path), 'backend web')
    assert text == 'backend web'
    assert section.rewrite_section(start, end, str(path), 'backend new').endswith('backend new')


def test_text_editor_does_not_consume_next_managed_marker(tmp_path):
    path = tmp_path / 'haproxy.cfg'
    tail = '# BEGIN Roxy-WI MANAGED backend web do not edit it directly\nbackend web\n# END Roxy-WI MANAGED backend web do not edit it directly\n'
    path.write_text('global\n daemon\n' + tail, encoding='utf-8', newline='')
    start, end, _ = section.get_section_from_config(str(path), 'global')
    assert section.rewrite_section(start, end, str(path), 'global\n maxconn 4000\n') == 'global\n maxconn 4000\n' + tail


def test_text_editor_disambiguates_headers_and_rejects_stale_line(tmp_path):
    path = tmp_path / 'haproxy.cfg'
    path.write_text('defaults\n timeout connect 5s\ndefaults\n timeout connect 10s\n', encoding='utf-8')
    with pytest.raises(ValueError, match='ambiguous'):
        section.get_section_from_config(str(path), 'defaults')
    assert section.get_section_from_config(str(path), 'defaults', 3)[0:2] == (2, 3)
    with pytest.raises(ValueError, match='reopen'):
        section.get_section_from_config(str(path), 'defaults', 2)


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_viewer_localization_is_complete_and_template_escapes_config(app, locale):
    with app.test_request_context('/'):
        g.user_params = {'group_id': 1}
        english = app.jinja_env.get_template('languages/en.html').module.config_viewer
        translated = app.jinja_env.get_template(f'languages/{locale}.html').module.config_viewer
        assert translated.keys() == english.keys()
        assert all(isinstance(value, str) and value for value in translated.values())
        text = 'backend "web\'\n # </script><script>alert(1)</script>\n'
        rendered = render_template('ajax/config_show.html', document=document(text), serv='192.0.2.11',
                                   service='haproxy', configver=None, hostname='test', lang=locale,
                                   config_file_name='', role=1, edit_section=None)
        assert '<script>alert(1)</script>' not in rendered
        serialized = re.search(r'class="cv-document">(.*?)</script>', rendered, re.S)[1]
        assert json.loads(serialized)['text'] == text
        assert translated['source'] in rendered
        assert f">{translated['copy']}</button>" in rendered
        assert 'built-in method' not in rendered


def test_selected_path_cannot_silently_fall_back_to_main(monkeypatch):
    monkeypatch.setattr(common.sql, 'get_setting', lambda name: '/etc/haproxy' if name == 'haproxy_dir' else '/etc/haproxy/haproxy.cfg')
    monkeypatch.setattr(common.common, 'check_is_conf', lambda path: True)
    assert common.resolve_viewer_path('haproxy') == '/etc/haproxy/haproxy.cfg'
    assert common.resolve_viewer_path('haproxy', '/etc/haproxy/conf.d/other.cfg') == '/etc/haproxy/conf.d/other.cfg'
    with pytest.raises(ValueError, match='HAProxy directory'):
        common.resolve_viewer_path('haproxy', '/etc/nginx/other.cfg')


def test_resolved_file_path_keeps_literal_92():
    assert config_mod._replace_config_path_to_correct('/etc/nginx/site92.conf') == '/etc/nginx/site92.conf'
    assert config_mod._replace_config_path_to_correct(encode_file_path('/etc/nginx/site92.conf')) == '/etc/nginx/site92.conf'
    with pytest.raises(ValueError):
        config_mod._replace_config_path_to_correct('92etc92nginx92site.conf')


def test_version_list_uses_owned_records_not_filename_prefix(monkeypatch, tmp_path):
    archive = tmp_path / 'versions'
    archive.mkdir()
    owned = archive / 'lb-prod-unique.cfg'
    owned.write_text('global\n', encoding='utf-8')
    (archive / 'lb-prod-untracked.cfg').write_text('global\n', encoding='utf-8')
    outside = tmp_path / 'outside.cfg'
    outside.write_text('global\n', encoding='utf-8')
    records = [SimpleNamespace(local_path=str(path)) for path in (owned, outside, archive / 'missing.cfg')]
    monkeypatch.setattr(config_mod.config_sql, 'select_config_version', lambda *args: iter(records))
    monkeypatch.setattr(config_mod.user_sql, 'select_users', lambda: [])
    monkeypatch.setattr(config_mod.roxywi_common, 'get_user_lang_for_flask', lambda: 'en')
    monkeypatch.setattr(common, 'get_config_dir', lambda *args: str(archive))
    monkeypatch.setattr(config_mod, 'render_template', lambda template, **kwargs: kwargs)
    result = config_mod.list_of_versions('lb-prod', 'haproxy', owned.name, 0)
    assert result['return_files'] == [owned.name]
    assert result['configs'] == records


@pytest.mark.parametrize('fail', [False, True])
def test_live_viewer_cleans_up_download_even_on_failure(monkeypatch, tmp_path, fail):
    path = tmp_path / 'download.cfg'
    monkeypatch.setattr(config_mod.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=11))
    monkeypatch.setattr(common, 'resolve_viewer_path', lambda *args: '/etc/haproxy/haproxy.cfg')
    monkeypatch.setattr(common, 'generate_config_path', lambda *args: str(path))
    def download(*args, **kwargs):
        path.write_bytes(b'global\r\n daemon\r\n')
        if fail:
            raise OSError('Download interrupted')
    monkeypatch.setattr(config_mod, 'get_config', download)
    if fail:
        with pytest.raises(OSError, match='interrupted'):
            config_mod.show_config('192.0.2.11', 'haproxy', None, None, {'user_id': 1, 'group': 1}, None)
    else:
        monkeypatch.setattr(config_mod.user_sql, 'get_user_role_in_group', lambda *args: 3)
        monkeypatch.setattr(config_mod.server_sql, 'is_serv_protected', lambda *args: True)
        monkeypatch.setattr(config_mod.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=11, group_id=1, hostname='test'))
        monkeypatch.setattr(config_mod.service_sql, 'select_service_setting', lambda *args: 0)
        monkeypatch.setattr(config_mod.sql, 'get_setting', lambda *args: '/etc/haproxy/haproxy.cfg')
        monkeypatch.setattr(config_mod.roxywi_common, 'get_user_lang_for_flask', lambda: 'en')
        monkeypatch.setattr(config_mod.deployment_policy, 'direct_deployment_allowed', lambda *args: True)
        monkeypatch.setattr(config_mod, 'render_template', lambda template, **kwargs: kwargs['document'])
        doc = config_mod.show_config('192.0.2.11', 'haproxy', None, None, {'user_id': 1, 'group': 1}, None)
        assert doc['text'] == 'global\r\n daemon\r\n'
        assert doc['edit_url'] is None
    assert not path.exists()
