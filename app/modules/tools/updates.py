"""Evidence-backed versions for the update page, without container-engine access."""

import json
from datetime import datetime, timezone
from pathlib import Path

from packaging.version import InvalidVersion, Version

from app.modules.db import roxy as roxy_sql, service_event
from app.modules.roxywi.roxy import deployment_mode
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.tools import common


INVENTORY_MAX_AGE = 120
INVENTORY_MAX_BYTES = 1024 * 1024


def parsed_version(value):
    if not isinstance(value, str) or not value.strip() or value.strip() == '0':
        return None
    try:
        return Version(value.strip())
    except InvalidVersion:
        return None


def load_inventory(now=None):
    config = GetConfigVar()
    lib_path = config.get_config_var('main', 'lib_path', '/var/lib/roxy-wi')
    path = Path(config.get_config_var(
        'main', 'deployment_inventory_file', f'{lib_path}/runtime/deployment-inventory.json',
    ))
    try:
        with path.open('rb') as stream:
            raw = stream.read(INVENTORY_MAX_BYTES + 1)
        if len(raw) > INVENTORY_MAX_BYTES:
            return None
        inventory = json.loads(raw)
        if inventory.get('schema') != 1 or inventory.get('complete') is not True:
            return None
        observed = datetime.fromisoformat(inventory['observed_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            return None
        age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
        if not 0 <= age <= INVENTORY_MAX_AGE:
            return None
        services = inventory['services']
        if not isinstance(services, list) or len(services) > 256:
            return None
        if any(not isinstance(item, dict) for item in services):
            return None
        for item in services:
            if not isinstance(item.get('service'), str) or len(item['service']) > 128:
                return None
            if not isinstance(item.get('running'), bool):
                return None
            value = item.get('version')
            if value is not None and (not isinstance(value, str) or len(value) > 128):
                return None
        return inventory
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def prepare_updates(services, mode, inventory=None, packages=None):
    """Do not turn database bootstrap defaults into installed container versions."""
    packages = packages or {}
    rows = []
    for name, status, stored, workers, management in services:
        version = dict(stored)
        metadata = dict(management)
        evidence = []
        source = 'unknown'
        reported = workers.get('versions', []) if workers.get('active', 0) else []
        if reported:
            evidence.extend(reported)
            source = 'worker'

        deployed = [item for item in (inventory or {}).get('services', [])
                    if item.get('service') == name]
        if deployed:
            # Image/package evidence also covers installed but stopped services.
            if not reported:
                evidence.extend(item.get('version') for item in deployed)
            source = 'worker' if reported else 'inventory'
            if not reported:
                status = 'active' if any(item.get('running') is True for item in deployed) else 'stopped'

        local_version = packages.get(name, {}).get('current_version') if mode == 'package' else None
        if parsed_version(local_version) is not None:
            evidence.append(local_version)
            if source == 'unknown':
                source = 'package'
        elif mode == 'package' and not packages and parsed_version(stored.get('current_version')):
            # Useful to callers with already refreshed package-only results.
            local_version = stored['current_version']
            evidence.append(local_version)
            source = 'package' if source == 'unknown' else source

        current = sorted({value.strip() for value in evidence
                          if isinstance(value, str) and parsed_version(value) is not None},
                         key=Version)
        latest = parsed_version(version.get('new_version'))
        version.update(
            current_version=', '.join(current),
            version_known=bool(current),
            version_source=source,
            need_update=bool(latest and any(Version(value) < latest for value in current)),
            latest_known=latest is not None,
        )
        local = parsed_version(local_version)
        has_local = bool(local_version and str(local_version) != '0'
                         and 'not installed' not in str(local_version))
        metadata.update(
            can_update_package=bool(mode == 'package' and local and latest and local < latest),
            can_install_package=bool(mode == 'package' and not has_local and not reported and not deployed),
            inventory_state=(
                'reported' if source != 'unknown' else
                'stale' if workers.get('stale', 0) else
                'not_detected' if inventory is not None else 'not_reported'
            ),
        )
        rows.append([name, status, version, workers, metadata])
    return rows


def get_update_services():
    mode = deployment_mode()
    workers = service_event.worker_summary()
    services = common.get_services_status(update_cur_ver=mode == 'package', worker_states=workers)
    packages = roxy_sql.get_all_tools() if mode == 'package' else {}
    return prepare_updates(services, mode, load_inventory(), packages)
