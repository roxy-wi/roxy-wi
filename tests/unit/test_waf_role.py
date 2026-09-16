from pathlib import Path

from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import pytest
import yaml


ROLE_DIR = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/waf'


def role_data():
    defaults = yaml.safe_load((ROLE_DIR / 'defaults/main.yml').read_text(encoding='utf-8'))
    tasks = yaml.safe_load((ROLE_DIR / 'tasks/main.yml').read_text(encoding='utf-8'))[0]
    return defaults, tasks


@pytest.mark.parametrize('distribution, major, expected', [
    ('CentOS', '9', ['crb']),
    ('Rocky', '9', ['crb']),
    ('AlmaLinux', '9', ['crb']),
    ('CentOS', '8', []),
    ('CentOS', '7', []),
    ('RedHat', '9', []),
    ('OracleLinux', '9', []),
    ('Ubuntu', '22', []),
])
def test_crb_is_scoped_to_supported_el9_package_transactions(distribution, major, expected):
    defaults, tasks = role_data()
    environment = NativeEnvironment(undefined=StrictUndefined)
    repositories = environment.from_string(defaults['waf_build_repositories']).render(
        ansible_facts={'distribution': distribution, 'distribution_major_version': major},
    )
    assert repositories == expected
    for name in ('install the el9 RPMS for HAProxy', 'install the common RPMS for HAProxy'):
        task = next(task for task in tasks['block'] if task['name'] == name)
        enabled = environment.from_string(task['yum']['enablerepo']).render(
            waf_build_repositories=repositories,
        )
        assert enabled == expected


def test_cleanup_can_render_before_build_facts_exist():
    _, tasks = role_data()
    cleanup = tasks['always'][0]
    environment = NativeEnvironment(undefined=StrictUndefined)
    paths = [environment.from_string(path).render() for path in cleanup['with_items']]
    assert len(paths) == len(set(paths))
    assert set(paths) == {
        '/tmp/modsecurity.tar.gz', '/tmp/spoa-modsecurity',
        '/tmp/owasp.tar.gz', '/tmp/owasp-modsecurity-crs-2.2.9',
    }


def test_modsecurity_include_directory_matches_copy_destination():
    _, tasks = role_data()
    directory = next(task for task in tasks['block'] if task['name'] == 'Creates directory')
    copy = next(task for task in tasks['block'] if task['name'] == 'Copy Modsec libs')
    environment = NativeEnvironment(undefined=StrictUndefined)
    variables = {'mod_sec_src': '/tmp/modsecurity/modsecurity-2.9.5'}
    path = environment.from_string(directory['file']['path']).render(**variables)
    destination = environment.from_string(copy['copy']['dest']).render(**variables)
    assert path == destination.rstrip('/')
