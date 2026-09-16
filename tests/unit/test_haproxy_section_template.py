from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
import pytest
import yaml

from app.modules.roxywi.class_models import HaproxyConfigRequest


ROLE_DIR = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/haproxy_section'


@pytest.fixture
def render_section():
    environment = Environment(
        loader=FileSystemLoader(str(ROLE_DIR / 'templates')),
        undefined=StrictUndefined,
        trim_blocks=True,
    )
    template = environment.get_template('section.j2')
    role_variables = yaml.safe_load((ROLE_DIR / 'vars/main.yml').read_text(encoding='utf-8'))

    def render(config, *, legacy_nulls=False):
        payload = config.model_dump(mode='json')
        if legacy_nulls:
            payload = {key: 'None' if value is None else value for key, value in payload.items()}
        return template.render(
            **role_variables, config=payload, cert_path='/etc/ssl', service_dir='/etc/haproxy',
        )

    return render


def section_config(section_type='listen', mode='http', **overrides):
    values = {'type': section_type, 'mode': mode, 'name': 'test_plain'}
    if section_type != 'backend':
        values['binds'] = [{'ip': '', 'port': 18080}]
    if section_type != 'frontend':
        values['backend_servers'] = [{
            'server': '192.0.2.12', 'port': 8080, 'port_check': 8080,
            'send_proxy': False, 'backup': False,
        }]
    values.update(overrides)
    return HaproxyConfigRequest(**values)


@pytest.mark.parametrize('section_type', ('listen', 'frontend', 'backend'))
@pytest.mark.parametrize('mode', ('http', 'tcp'))
@pytest.mark.parametrize('legacy_nulls', (False, True), ids=('json-null', 'legacy-None-string'))
def test_sections_without_ssl_render_optional_defaults(render_section, section_type, mode, legacy_nulls):
    config = section_config(section_type, mode, ssl=None)

    rendered = render_section(config, legacy_nulls=legacy_nulls)
    lines = [' '.join(line.split()) for line in rendered.splitlines() if line.strip()]

    assert f'{section_type} test_plain' in lines
    assert f'mode {mode}' in lines
    assert 'None' not in rendered
    assert 'ssl crt' not in rendered
    assert 'ssl verify' not in rendered
    if section_type != 'backend':
        assert 'bind :18080' in lines
    else:
        assert 'bind ' not in rendered
    if section_type != 'frontend':
        assert 'server 192.0.2.12 192.0.2.12:8080 port 8080 maxconn 2000' in lines


@pytest.mark.parametrize('verify_backend', (False, True))
@pytest.mark.parametrize('http2', (False, True))
def test_ssl_certificate_and_backend_verification_are_preserved(render_section, verify_backend, http2):
    config = section_config(
        ssl={'cert': 'test.pem', 'ssl_check_backend': verify_backend}, http2=http2,
    )

    rendered = render_section(config)

    assert 'ssl crt /etc/ssl/test.pem' in rendered
    expected_verification = 'required' if verify_backend else 'none'
    assert f'ssl verify {expected_verification}' in rendered
    assert ('alpn h2,http/1.1' in rendered) is http2


@pytest.mark.parametrize('legacy_nulls', (False, True))
def test_http_acl_without_ssl_uses_host_header(render_section, legacy_nulls):
    config = section_config(
        'frontend',
        acls=[{'acl_if': 1, 'acl_then': 5, 'acl_then_value': 'test_backend', 'acl_value': 'example.com'}],
    )

    rendered = render_section(config, legacy_nulls=legacy_nulls)

    assert 'use_backend test_backend if { hdr_beg(host) -i example.com }' in rendered
    assert 'ssl_fc_sni' not in rendered


def test_listener_without_bind_address_does_not_render_none(render_section):
    rendered = render_section(section_config(binds=[{'port': 18080}]))

    assert 'bind :18080' in rendered
    assert 'None' not in rendered


def test_backend_server_template_handles_absent_server_list(render_section):
    config = section_config(
        'backend', backend_servers=None,
        servers_template={'prefix': 1, 'count': 3, 'servers': 'example.com', 'port': 8080},
    )

    rendered = render_section(config)

    assert 'server-template 1 3 example.com:' in rendered
    assert 'None' not in rendered


def test_listener_without_ssl_preserves_enabled_options(render_section):
    config = section_config(
        balance='leastconn',
        health_check={'check': 'httpchk', 'path': '/'},
        servers_check={'check_enabled': True, 'inter': 3000, 'rise': 3, 'fall': 4},
        headers=[{'path': 'http-request', 'method': 'set-header', 'name': 'X-Test', 'value': 'test'}],
        circuit_breaking={'observe': 'layer7', 'error_limit': 5, 'on_error': 'mark-down'},
        option='timeout connect 5s',
    )

    rendered = render_section(config)

    for expected in ('balance leastconn', 'option httpchk', 'check inter 3000 rise 3 fall 4',
                     'http-request set-header X-Test test', 'timeout connect 5s',
                     'default-server observe layer7 error-limit 5 on-error mark-down'):
        assert expected in rendered
    assert 'ssl crt' not in rendered
    assert 'ssl verify' not in rendered
    assert 'None' not in rendered
