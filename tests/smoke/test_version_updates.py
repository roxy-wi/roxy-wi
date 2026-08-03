from app import jobs
import app.modules.db.roxy as roxy_sql
from app.modules.db.db_model import RoxyTool
from app.modules.roxywi import roxy
from app.version import get_service_version


class _VersionResponse:
    def __init__(self, text=''):
        self.content = text.encode('utf-8')


def test_application_update_status_uses_existing_roxy_tools_table():
    RoxyTool.delete().where(RoxyTool.name == 'roxy-wi').execute()
    try:
        roxy_sql.update_app_versions(get_service_version(), '99.0.0')

        assert roxy_sql.get_tool_new_version('roxy-wi') == '99.0.0'
        assert 'roxy-wi' not in roxy_sql.get_all_tools()
    finally:
        RoxyTool.delete().where(RoxyTool.name == 'roxy-wi').execute()


def test_version_status_reads_existing_database_state(monkeypatch):
    monkeypatch.setattr(roxy.roxy_sql, 'get_tool_new_version', lambda _tool: '99.0.0')
    monkeypatch.setattr(
        roxy,
        'check_new_version',
        lambda _service: (_ for _ in ()).throw(AssertionError('unexpected external request')),
    )

    assert roxy.versions() == {
        'current_ver': get_service_version(),
        'new_ver': '99.0.0',
        'need_update': 1,
    }


def test_existing_component_update_cycle_also_updates_roxywi(monkeypatch):
    checks = []
    component_updates = []
    app_updates = []
    discovered = {
        'roxy-wi-checker': '2.0.0',
        'roxy-wi-smon': '3.0.0',
        'roxy-wi': '99.0.0',
    }

    def check(service):
        checks.append(service)
        return discovered[service]

    monkeypatch.setattr(
        jobs.roxy_sql,
        'get_roxy_tools',
        lambda: ['roxy-wi-checker', 'roxy-wi-smon'],
    )
    monkeypatch.setattr(jobs.roxy, 'check_new_version', check)
    monkeypatch.setattr(jobs.roxy, 'check_ver', get_service_version)
    monkeypatch.setattr(
        jobs.roxy_sql,
        'update_tool_new_version',
        lambda tool, version: component_updates.append((tool, version)),
    )
    monkeypatch.setattr(
        jobs.roxy_sql,
        'update_app_versions',
        lambda current, latest: app_updates.append((current, latest)),
    )

    jobs.update_new_versions()

    assert checks == ['roxy-wi-checker', 'roxy-wi-smon', 'roxy-wi']
    assert component_updates == [
        ('roxy-wi-checker', '2.0.0'),
        ('roxy-wi-smon', '3.0.0'),
    ]
    assert app_updates == [(get_service_version(), '99.0.0')]


def test_roxywi_update_check_keeps_statistics_delivery(monkeypatch):
    requested_urls = []

    def request(url, **_kwargs):
        requested_urls.append(url)
        return _VersionResponse('99.0.0')

    monkeypatch.setattr(roxy.common, 'return_proxy_dict', lambda: {})
    monkeypatch.setattr(roxy.requests, 'get', request)

    assert roxy.check_new_version('roxy-wi') == '99.0.0'
    assert requested_urls == [
        'https://roxy-wi.org/version/get/roxy-wi',
        f'https://roxy-wi.org/version/send/{get_service_version()}',
    ]
