import hashlib
import json
from pathlib import Path
import runpy
import re
import shlex
from types import SimpleNamespace

from jinja2 import Environment, StrictUndefined
import pytest
import yaml

from app.modules.config import candidate


ROLE = Path(__file__).resolve().parents[3] / 'app/scripts/ansible/roles/waf_nginx'
build_options = runpy.run_path(str(ROLE / 'files/build_options.py'))['build_options']


def test_build_options_match_the_binary_and_preserve_quoted_compiler_arguments():
    output = ('nginx version: nginx/1.26.2\nbuilt with OpenSSL\nconfigure arguments: '
              "--prefix=/usr/share/nginx --with-cc-opt='-O2 -fPIC' --with-compat "
              '--add-module=/build/removed --add-dynamic-module=/build/also-removed --with-http_ssl_module\n')
    assert build_options(output) == dict(version='1.26.2', arguments=[
        '--prefix=/usr/share/nginx', '--with-cc-opt=-O2 -fPIC', '--with-compat', '--with-http_ssl_module'])


@pytest.mark.parametrize('output', ['nginx version: nginx/1.26.2\n', 'nginx version: openresty/1.26.1\nconfigure arguments: --with-compat'])
def test_unknown_build_inputs_fail_instead_of_guessing_a_source_version(output):
    with pytest.raises(ValueError, match='Cannot determine'):
        build_options(output)


def test_build_options_add_compat_without_running_shell_metacharacters():
    assert build_options("nginx version: nginx/1.24.0\nconfigure arguments: --with-cc-opt='$(id); x'") == dict(
        version='1.24.0', arguments=['--with-cc-opt=$(id); x', '--with-compat'])


@pytest.mark.parametrize('arguments,required', [
    (['--with-http_realip_module', '--with-compat'], False),
    (['--with-http_geoip_module=dynamic'], True),
    (['--with-stream_geoip_module'], True),
])
def test_rhel_build_requires_geoip_only_when_present_in_the_binary(arguments, required):
    tasks = yaml.safe_load((ROLE / 'tasks/build_module.yml').read_text())
    packages = next(task['yum']['name'] for task in tasks if 'yum' in task)
    assert 'GeoIP-devel' not in packages
    assert 'libmodsecurity-devel' in packages
    geoip = next(task for task in tasks if task.get('ansible.builtin.yum', {}).get('name') == 'GeoIP-devel')
    environment = Environment(undefined=StrictUndefined)
    environment.tests['search'] = lambda value, pattern: re.search(pattern, value) is not None
    assert all(environment.compile_expression(expression)(
        ansible_facts={'os_family': 'RedHat'}, waf_nginx_build={'arguments': arguments})
        for expression in geoip['when']) is required


def test_nginx_install_and_waf_editor_share_the_lock():
    root = '/srv/web/waf'
    commands = [shlex.split(candidate.candidate_command(
        service, target, '/tmp/upload', 'save', main='/etc/custom.conf', root=root))
        for service, target in [('nginx', '/etc/custom.conf'), ('nginx_waf', root + '/rules/test.conf')]]
    assert commands[0][5] == commands[1][5]


@pytest.mark.parametrize('failure', ['', 'validation', 'reload', 'stale', 'other_target'])
def test_nginx_main_transaction_checks_the_whole_tree_and_recovers(tmp_path, monkeypatch, failure):
    main = tmp_path / 'main with spaces.conf'
    main.write_bytes(b'# original\n')
    upload = tmp_path / 'candidate.conf'
    upload.write_bytes(b'# replacement\n')
    calls = []
    results = {'validation': [0, 1], 'reload': [0, 0, 1, 0, 0]}.get(failure, [0, 0, 0])

    def run(args, **kwargs):
        calls.append((args, main.read_bytes()))
        return SimpleNamespace(returncode=results.pop(0), stdout=b'private config output')

    monkeypatch.setattr(candidate, '_run', run)
    spec = dict(service='nginx', target=str(main), main=str(main), candidate=str(upload), action='reload',
                action_command='systemctl reload custom-nginx', expected_sha256=hashlib.sha256(main.read_bytes()).hexdigest())
    if failure == 'stale':
        spec['expected_sha256'] = 'a' * 64
    elif failure == 'other_target':
        other = tmp_path / 'other.conf'
        other.write_text('unchanged')
        spec['target'] = str(other)
    response = candidate.execute(spec)
    if failure:
        assert response['status'] == 'failed'
        assert main.read_bytes() == b'# original\n'
        if failure in ('stale', 'other_target'):
            assert not calls
        elif failure == 'validation':
            assert all(args[0] == 'nginx' for args, _ in calls)
        else:
            assert calls[-1][1] == b'# original\n'
    else:
        assert response == {'status': 'ok'}
        assert calls == [(['nginx', '-t', '-c', str(main)], b'# original\n'),
                         (['nginx', '-t', '-c', str(main)], b'# replacement\n'),
                         (['sh', '-c', spec['action_command']], b'# replacement\n')]
    assert 'private' not in json.dumps(response)
    assert not upload.exists()


def test_rules_template_quotes_custom_paths():
    environment = Environment(undefined=StrictUndefined)
    environment.filters['to_json'] = json.dumps
    rendered = environment.from_string((ROLE / 'templates/waf.conf.j2').read_text()).render(SERVICE_PATH='/srv/web configs')
    includes = [shlex.split(line) for line in rendered.splitlines()]
    assert all(len(line) == 2 and line[0] == 'Include' and line[1].startswith('/srv/web configs/waf/') for line in includes)


def test_unicode_mapping_is_raw_versioned_and_resolves_from_any_nginx_prefix():
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())[0]['block']
    defaults = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())
    environment = Environment(undefined=StrictUndefined)
    environment.filters['to_json'] = json.dumps
    variables = {**defaults, 'SERVICE_PATH': '/srv/web configs'}
    urls = [task['ansible.builtin.get_url']['url'] for task in tasks if 'ansible.builtin.get_url' in task]
    mapping_url = next(url for url in urls if url.endswith('/unicode.mapping'))
    assert environment.from_string(mapping_url).render(**variables) == (
        'https://raw.githubusercontent.com/owasp-modsecurity/ModSecurity/v3.0.7/unicode.mapping')
    mapping = next(task['ansible.builtin.lineinfile'] for task in tasks if 'ansible.builtin.lineinfile' in task)
    directive = environment.from_string(mapping['line']).render(**variables)
    # ModSecurity reads the unquoted path up to the final code-page argument.
    assert directive == 'SecUnicodeMapFile /srv/web configs/waf/unicode.mapping 20127'
