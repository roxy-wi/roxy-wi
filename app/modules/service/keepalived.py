"""Shared Keepalived observation for Checker and the HA interface."""
import json
from pathlib import Path

from app.modules.connectors import containers, keepalived as probe
from app.modules.db import service as service_sql
from app.modules.integrations.keepalived_contract import KeepalivedSnapshot
from app.modules.pacemaker.remote import Remote
from app.modules.service import container_settings


def probe_settings(server) -> dict:
    """Resolve the saved binding without discovering or falling back to a host."""
    if service_sql.select_service_setting(server.server_id, 'keepalived', 'dockerized') == '1':
        runtime = container_settings.runtime(server.server_id, 'keepalived')
        if runtime['owner'] != 'root':
            raise ValueError('Keepalived requires a rootful host-network container')
        return dict(runtime=runtime, name=container_settings.name(server.server_id, 'keepalived'))
    return {}


def collect(server) -> KeepalivedSnapshot:
    """Use the server's existing SSH identity and configured container binding."""
    source = Path(probe.__file__).read_text(encoding='utf-8')
    data = probe_settings(server)
    prefix = containers.embedded() if data else ''
    source = prefix + source + '''
import json, sys
data = json.load(sys.stdin)
record = module.container_state(data['runtime'], data['name']) if data else None
result = collect(record)
if data:
    current = module.container_state(data['runtime'], data['name'])
    if (current.get('Id', current.get('ID')) != record.get('Id', record.get('ID')) or
            any(current['State'].get(key) != record['State'].get(key)
                for key in ('Pid', 'Running', 'Restarting', 'Paused', 'StartedAt'))):
        raise ValueError('Container changed during the probe')
print(json.dumps(result))
'''
    output = Remote(server).run(['python3', '-c', source], data=json.dumps(data), timeout=45)
    if probe_settings(server) != data:
        raise ValueError('Keepalived binding changed during the probe')
    return KeepalivedSnapshot.model_validate_json(output)


def summary(snapshot: KeepalivedSnapshot) -> str:
    """Keep the existing single-label UI, giving faults precedence over roles."""
    if snapshot.service == 'DOWN':
        return 'DOWN'
    states = {instance.state for instance in snapshot.instances}
    return next(state for state in ('FAULT', 'INIT', 'MASTER', 'BACKUP') if state in states)
