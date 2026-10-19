"""Exercise the transaction with an isolated NGINX tree and real HTTP traffic.

The included file uses an NGINX map to test full-tree validation without needing
the optional ModSecurity module. No system service or production path is used.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pytest
import yaml
from ansible.module_utils.common.json import AnsibleJSONEncoder
from ansible.utils.unsafe_proxy import wrap_var

from app.modules.config import candidate as transaction
from app.modules.config.waf_wizard import DEFAULT, render_rule
from app.modules.roxywi.waf_rule_file import create_rule
from app.modules.service.nginx import waf_configuration_candidate


pytestmark = pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('nginx') or not shutil.which('flock'),
                                reason='Linux with nginx and flock required')


def wait_for_response(url, expected):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.read() == expected:
                    return
        except OSError:
            pass
        time.sleep(0.05)
    pytest.fail(f'NGINX did not return {expected!r}')


@pytest.fixture
def nginx(tmp_path):
    (tmp_path / 'waf/rules').mkdir(parents=True)
    target = tmp_path / 'waf/rules/test.conf'
    target.write_text('map $http_host $waf_test { default old; }\n')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    main = tmp_path / "nginx's main.conf"
    temporary_paths = '\n'.join(f'{kind}_temp_path "{tmp_path / kind}";' for kind in
                                ('client_body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'))
    main.write_text(f'''pid "{tmp_path / 'nginx.pid'}";
error_log "{tmp_path / 'error.log'}";
events {{}}
http {{
    access_log off;
    {temporary_paths}
    include "{target}";
    server {{ listen 127.0.0.1:{port}; return 200 "$waf_test"; }}
}}
''')
    process = subprocess.Popen(['nginx', '-c', str(main), '-p', str(tmp_path), '-e', str(tmp_path / 'startup.log'),
                                '-g', 'daemon off;'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f'http://127.0.0.1:{port}/'
    try:
        wait_for_response(url, b'old')
        yield tmp_path, target, main, url
    finally:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def run_transaction(root, target, main, text, action, executable=sys.executable):
    candidate = root / 'upload.conf'
    candidate.write_text(text)
    args = json.dumps(dict(service='nginx_waf', target=str(target), candidate=str(candidate), main=str(main),
                           action='reload' if action else 'save', action_command=action))
    result = subprocess.run(['flock', '-w', '5', str(root / 'waf.lock'), executable,
                             str(Path(transaction.__file__)), args], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_default_host_python_can_save_apply_and_clean_up(nginx):
    # The managed host's python3 can be older than the application's Python.
    # CentOS Stream 8, for example, invokes Python 3.6 through sudo python3.
    root, target, main, url = nginx
    executable = shutil.which('python3')
    if not executable:
        pytest.skip('Host python3 is unavailable')
    response = run_transaction(root, target, main, 'map $http_host $waf_test { default legacy; }\n',
                               shlex.join(['nginx', '-c', str(main), '-s', 'reload']), executable=executable)
    assert response == {'status': 'ok'}
    wait_for_response(url, b'legacy')
    assert not list(root.rglob('.roxywi-*'))
    assert not (root / 'upload.conf').exists()


def test_diagnostics_validate_only_included_files_without_reload(nginx, monkeypatch):
    root, target, main, url = nginx
    entrypoint = root / 'waf/modsecurity.conf'
    entrypoint.write_text('SecRuleEngine On\n')
    # A recursive grep would report this inactive file as enabled protection.
    (root / 'inactive.conf').write_text('modsecurity on;\n')
    pid = int((root / 'nginx.pid').read_text())
    run = transaction._run

    def checked_run(args, **kwargs):
        if args[:2] == ['systemctl', 'show']:
            output = b'loaded' if '--property=LoadState' in args else f'MainPID={pid}\nActiveState=active\nSubState=running'.encode()
            return SimpleNamespace(returncode=0, stdout=output)
        assert args == ['nginx', '-T', '-c', str(main)]
        return run(args, **kwargs)

    monkeypatch.setattr(transaction, '_run', checked_run)
    before = {path: path.read_bytes() for path in (main, target, entrypoint)}
    result = transaction.execute(dict(service='nginx_waf', action='status', candidate='', target=str(entrypoint),
                                      main=str(main), service_unit='nginx'))
    assert result == dict(status='ok', process='running', check='valid', module='not_configured', error='')
    assert {path: path.read_bytes() for path in before} == before
    assert int((root / 'nginx.pid').read_text()) == pid
    wait_for_response(url, b'old')


def test_invalid_candidate_is_restored_and_valid_reload_changes_live_response(nginx):
    root, target, main, url = nginx
    original = target.read_bytes()
    reload_command = shlex.join(['nginx', '-c', str(main), '-s', 'reload'])
    result = run_transaction(root, target, main, 'unknown_waf_directive;\n', reload_command)
    assert result['code'] == 'validation_failed'
    assert target.read_bytes() == original
    wait_for_response(url, b'old')
    result = run_transaction(root, target, main, 'map $http_host $waf_test { default new; }\n', reload_command)
    assert result == {'status': 'ok'}
    wait_for_response(url, b'new')
    assert not list(root.rglob('.roxywi-*'))


def test_failed_reload_recovers_previous_configuration_and_http_response(nginx):
    root, target, main, url = nginx
    marker = root / 'first-action'
    reload_command = shlex.join(['nginx', '-c', str(main), '-s', 'reload'])
    action = f'if [ ! -f {shlex.quote(str(marker))} ]; then touch {shlex.quote(str(marker))}; exit 1; fi; {reload_command}'
    result = run_transaction(root, target, main, 'map $http_host $waf_test { default new; }\n', action)
    assert result['code'] == 'apply_failed'
    assert target.read_text() == 'map $http_host $waf_test { default old; }\n'
    wait_for_response(url, b'old')
    assert not list(root.rglob('.roxywi-*'))


@pytest.fixture
def nginx_install(nginx):
    root, target, main, url = nginx
    if not shutil.which('ansible-playbook'):
        pytest.skip('Ansible required')
    module = next((path for path in (
        Path('/usr/lib/nginx/modules/ngx_http_modsecurity_module.so'),
        Path('/usr/lib64/nginx/modules/ngx_http_modsecurity_module.so'),
        Path('/etc/nginx/waf/modules/ngx_http_modsecurity_module.so'),
    ) if path.is_file()), None)
    if module is None:
        pytest.skip('NGINX ModSecurity module required')
    # NGINX main paths may contain quotes; ModSecurity Include paths cannot.
    service_root = root / 'custom-web'
    modules = service_root / 'waf/modules'
    modules.mkdir(parents=True)
    shutil.copyfile(module, modules / module.name)
    rules = service_root / 'waf/rules'
    rules.mkdir()
    rule = rules / 'custom.conf'
    rule.write_text('SecRuleEngine DetectionOnly\n')
    mapping = service_root / 'waf/unicode.mapping'
    mapping.write_text('20127 (US-ASCII)\n0041:0061\n')
    (service_root / 'waf/waf.conf').write_text(f'SecUnicodeMapFile {mapping} 20127\nInclude "{rule}"\n')
    temporary = root / 'temporary'
    temporary.mkdir()
    tasks = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/waf_nginx/tasks/nginx_config.yml'

    def run(*, loaded=False, action=None, main_path=main):
        action = action or shlex.join(['nginx', '-c', str(main), '-s', 'reload'])
        command = shlex.split(transaction.candidate_command(
            'nginx', str(main_path), '', 'reload', main=str(main_path), root=str(service_root / 'waf'), action_command=action))
        command = command[2:]
        command[3] = str(root / 'config.lock')
        command[4] = sys.executable
        inventory = {'all': {'hosts': {'localhost': {
            'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
            'NGINX_CONFIG_PATH': str(main_path), 'NGINX_CONFIG_COMMAND': command,
            'SERVICE_PATH': str(service_root), 'waf_nginx_module_loaded': loaded,
        }}}}
        inventory_path = root / 'inventory.json'
        inventory_path.write_text(json.dumps(wrap_var(inventory), cls=AnsibleJSONEncoder, preprocess_unsafe=True))
        playbook = root / 'play.yml'
        playbook.write_text(yaml.safe_dump([{
            'hosts': 'all', 'gather_facts': False, 'become': False,
            'environment': {'TMPDIR': str(temporary)},
            'tasks': [{'ansible.builtin.include_tasks': str(tasks)}],
        }]))
        result = subprocess.run(['ansible-playbook', '-i', str(inventory_path), str(playbook)],
                                env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(root / 'ansible-tmp')},
                                text=True, capture_output=True, timeout=60)
        assert not list(temporary.glob('roxywi-*')), result.stdout
        return result

    return SimpleNamespace(main=main, other=target, rule=rule, root=service_root, run=run, url=url)


def test_install_connects_modsecurity_in_the_configured_main_and_preserves_enabled_state(nginx_install):
    state = nginx_install
    before = state.other.read_bytes()
    result = state.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert state.main.read_text().count('ngx_http_modsecurity_module.so') == 1
    assert f'modsecurity_rules_file "{state.root}/waf/waf.conf";' in state.main.read_text()
    assert not (state.root / 'nginx.conf').exists()
    state.main.write_text(state.main.read_text().replace('modsecurity off;', 'modsecurity on;'))
    state.rule.write_text('SecRuleEngine DetectionOnly\n# administrator edit\n')
    result = state.run(loaded=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert state.main.read_text().count('modsecurity on;') == 1
    assert state.main.read_text().count('ngx_http_modsecurity_module.so') == 1
    assert state.other.read_bytes() == before
    assert '# administrator edit' in state.rule.read_text()
    wait_for_response(state.url, b'old')


@pytest.mark.parametrize('failure', ['rule', 'other_include', 'reload'])
def test_installation_failure_restores_main_without_stopping_nginx(nginx_install, failure):
    state = nginx_install
    before = state.main.read_bytes()
    action = None
    if failure == 'rule':
        state.rule.write_text('NotAModSecurityDirective value\n')
    elif failure == 'other_include':
        state.other.write_text('unknown_nginx_directive;\n')
    else:
        marker = state.main.parent / 'failed-once'
        reload_command = shlex.join(['nginx', '-c', str(state.main), '-s', 'reload'])
        action = f'if [ ! -f {shlex.quote(str(marker))} ]; then touch {shlex.quote(str(marker))}; exit 1; fi; {reload_command}'
    result = state.run(action=action)
    assert result.returncode != 0, result.stdout
    assert ('apply_failed' if failure == 'reload' else 'validation_failed') in result.stdout
    assert state.main.read_bytes() == before
    wait_for_response(state.url, b'old')


def test_installation_preserves_main_symlink_and_relative_include_prefix(nginx_install):
    state = nginx_install
    real_main = state.main.parent / 'physical/main.conf'
    real_main.parent.mkdir()
    real_main.write_text(state.main.read_text().replace(f'include "{state.other}";', 'include waf/rules/test.conf;'))
    state.main.unlink()
    state.main.symlink_to(real_main)
    result = state.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert state.main.is_symlink()
    assert 'modsecurity_rules_file' in real_main.read_text()
    wait_for_response(state.url, b'old')


def test_main_waf_switch_changes_real_request_filtering(nginx_install):
    state = nginx_install
    public = state.main.parent / 'public'
    public.mkdir()
    (public / 'index.html').write_text('allowed')
    state.main.write_text(state.main.read_text().replace('return 200 "$waf_test";', f'root "{public}";'))
    state.rule.write_text('SecRuleEngine On\nSecRule ARGS:blocked "@streq 1" "id:100001,phase:1,deny,status:403,nolog"\n')
    result = state.run()
    assert result.returncode == 0, result.stdout + result.stderr
    for enabled in (False, True, True, False):
        original = state.main.read_bytes()
        upload = state.main.parent / 'switch.conf'
        upload.write_text(waf_configuration_candidate(original.decode(), enabled))
        command = shlex.split(transaction.candidate_command(
            'nginx', str(state.main), str(upload), 'reload', main=str(state.main), root=str(state.root / 'waf'),
            expected_sha256=hashlib.sha256(original).hexdigest(),
            action_command=shlex.join(['nginx', '-c', str(state.main), '-s', 'reload'])))[2:]
        command[3] = str(state.main.parent / 'config.lock')
        command[4] = sys.executable
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'status': 'ok'}
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(state.url + '?blocked=1', timeout=1) as response:
                    status = response.status
            except HTTPError as error:
                status = error.code
                error.close()
            if status == (403 if enabled else 200):
                break
            assert time.monotonic() < deadline, f'Unexpected HTTP {status} with WAF enabled={enabled}'
            time.sleep(0.05)
        wait_for_response(state.url, b'allowed')
        assert not upload.exists()


def test_wizard_generated_rules_and_scoped_exclusion_filter_real_requests(nginx_install):
    state = nginx_install
    public = state.main.parent / 'wizard-public'
    public.mkdir()
    for filename in ('index.html', 'blocked', 'submit', 'other', 'and', 'or'):
        (public / filename).write_text('allowed')
    state.main.write_text(state.main.read_text().replace('return 200 "$waf_test";', f'root "{public}";'))
    # A CRS-like rule also sees ARGS:other: the generated exclusion must only
    # exempt ARGS:body at /submit, not disable the engine or the whole ruleset.
    state.rule.write_text('SecRuleEngine On\nSecRequestBodyAccess On\n'
                          'SecRule ARGS "@contains attack" "id:942100,phase:2,t:none,deny,status:403,nolog"\n')
    entry = state.root / 'waf/waf.conf'
    specs = [
        {**DEFAULT, 'value': '/blocked'},
        {**DEFAULT, 'id': 10001, 'kind': 'exclusion', 'value': '/submit',
         'exclude_id': 942100, 'exclude_parameter': 'body'},
        {**DEFAULT, 'id': 10002, 'field': 'arg', 'key': 'log', 'value': 'record', 'action': 'log'},
        {**DEFAULT, 'id': 10003, 'field': 'header', 'key': 'X-Wizard', 'value': 'a"b\\%{danger}'},
        {**DEFAULT, 'id': 10004, 'field': 'ip', 'value': '127.0.0.1', 'action': 'log'},
        dict(version=2, id=10005, kind='rule', action='deny', match='all', exclude_id=0, exclude_parameter='',
             conditions=[dict(field='uri', key='', operator='equals', value='/and'),
                         dict(field='header', key='X-Block', operator='equals', value='yes')]),
        dict(version=2, id=10006, kind='rule', action='deny', match='any', exclude_id=0, exclude_parameter='',
             conditions=[dict(field='uri', key='', operator='equals', value='/or'),
                         dict(field='header', key='X-Or-Block', operator='equals', value='yes')]),
        # ctl must run only if BOTH conditions match, including on v2 engines.
        dict(version=2, id=10008, kind='exclusion', action='log', match='all', exclude_id=942100, exclude_parameter='body',
             conditions=[dict(field='uri', key='', operator='equals', value='/and'),
                         dict(field='header', key='X-Exclude', operator='equals', value='yes')]),
        dict(version=2, id=10009, kind='rule', action='deny', match='all', exclude_id=0, exclude_parameter='',
             conditions=[dict(field='uri', key='', operator='equals', value='/and'),
                         dict(field='arg', key='token', operator='equals', value='blocked')]),
    ]
    for index, spec in enumerate(specs):
        target = state.root / f'waf/rules/wizard-{index}.conf'
        create_rule(entry, target, str(index) * 64, before_rules=True)
        target.write_text(render_rule(spec))
    installed = state.run()
    assert installed.returncode == 0, installed.stdout + installed.stderr
    state.main.write_text(state.main.read_text().replace('modsecurity off;', 'modsecurity on;'))
    enabled = state.run(loaded=True)
    assert enabled.returncode == 0, enabled.stdout + enabled.stderr
    for suffix, headers, expected in [('/blocked', {}, 403), ('/submit?body=attack', {}, 200),
                                      ('/other?body=attack', {}, 403), ('/submit?other=attack', {}, 403),
                                      ('/?log=record', {}, 200), ('/', {'X-Wizard': 'a"b\\%{danger}'}, 403),
                                      ('/and', {}, 200), ('/and', {'X-Block': 'yes'}, 403),
                                      ('/other', {'X-Block': 'yes'}, 200),
                                      ('/or', {}, 403), ('/other', {'X-Or-Block': 'yes'}, 403),
                                      ('/and?body=attack', {'X-Exclude': 'yes'}, 200),
                                      ('/and?body=attack', {}, 403),
                                      ('/other?body=attack', {'X-Exclude': 'yes'}, 403),
                                      ('/and?token=blocked', {}, 403), ('/other?token=blocked', {}, 200)]:
        request = Request(urljoin(state.url, suffix), headers=headers)
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(request, timeout=1) as response:
                    status = response.status
            except HTTPError as error:
                status = error.code
                error.close()
            if status == expected:
                break
            assert time.monotonic() < deadline, f'{request.full_url}: HTTP {status}, expected {expected}'
            time.sleep(0.05)


def test_crs_install_populates_existing_directory_and_preserves_edits(tmp_path):
    source = tmp_path / 'distribution/coreruleset-test/rules'
    source.mkdir(parents=True)
    (source / 'rule.conf').write_text('# distributed rule\n')
    (source / 'lookup.data').write_text('lookup value\n')
    destination = tmp_path / 'nginx/waf/rules'
    destination.mkdir(parents=True)
    tasks = yaml.safe_load((Path(__file__).resolve().parents[2] /
                            'app/scripts/ansible/roles/waf_nginx/tasks/main.yml').read_text())[0]['block']
    copy_tasks = [task for task in tasks if task['name'] in (
        'Find the distributed CRS rule and data files', 'Install missing CRS files without overwriting user edits')]
    playbook = tmp_path / 'install-rules.yml'
    playbook.write_text(yaml.safe_dump([{
        'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': {'ansible_python_interpreter': sys.executable, 'waf_nginx_work': {'path': str(tmp_path / 'distribution')},
                 'coreruleset_ver': 'test', 'SERVICE_PATH': str(tmp_path / 'nginx')},
        'tasks': copy_tasks,
    }]))
    for repeat in (False, True):
        if repeat:
            (destination / 'rule.conf').write_text('# administrator edit\n')
            (destination / 'lookup.data').unlink()
        result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook', '-i', 'localhost,', str(playbook)],
                                env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-tmp')},
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (destination / 'rule.conf').read_text() == ('# administrator edit\n' if repeat else '# distributed rule\n')
        assert (destination / 'lookup.data').read_text() == 'lookup value\n'
