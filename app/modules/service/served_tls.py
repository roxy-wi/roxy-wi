"""One-time certificate deployment evidence, recorded in its owning operation."""
import re

from app.modules.common.execution_context import group_settings
from app.modules.common.time import utc_iso, utc_now
from app.modules.connectors import containers
from app.modules.service import proxy_assessments as assessments
from app.modules.service import published_endpoints as inventory, network_probe as network

MAX_PROBES = 32
MAX_TARGETS = 32
MAX_NAMES = 100


def matches(name, pattern):
    if pattern.startswith('*.'):
        return name.endswith(pattern[1:]) and name.count('.') == pattern.count('.')
    return name == pattern


def report(endpoints, expected):
    fingerprints = {item['fingerprint'] for item in endpoints if item.get('fingerprint')}
    mismatch = bool(fingerprints - {expected})
    complete = bool(endpoints) and all(item.get('state') == 'verified' for item in endpoints)
    observed_all = bool(endpoints) and all(item.get('fingerprint') and item.get('state') in ('verified', 'mismatch')
                                         for item in endpoints)
    return dict(state='mismatch' if mismatch else 'verified' if complete else 'incomplete',
                expected_fingerprint=expected,
                peer_consistent=False if len(fingerprints) > 1 else len(fingerprints) == 1 if observed_all else None,
                observed_at=utc_iso(utc_now()), endpoints=endpoints)


def candidates(found, names):
    result = set()
    for front in found['frontends']:
        if not front['tls']:
            continue
        # Without explicit host routing, concrete certificate names supply SNI.
        domains = ({name for name in front['domains'] if any(matches(name, pattern) for pattern in names)}
                   if front['domains'] else {name for name in names if not name.startswith('*.')})
        for listener in front.get('tls_listeners', front['listeners']):
            for domain in sorted(domains):
                result.add((domain, listener['host'], listener['port']))
                if len(result) > MAX_PROBES:
                    return sorted(result)
    return sorted(result)


def verify(targets, metadata, group_id, user_id, *, heartbeat=lambda: None):
    """Inspect selected proxy listeners only after deployment has committed.

    Fingerprint agreement proves delivery of the expected leaf. Trust is reported
    separately: private PKI need not be trusted by the probe host. No HTTP, DNS,
    expiry threshold, periodic scheduling or standalone monitor is involved.
    """
    try:
        return _verify(targets, metadata, group_id, user_id, heartbeat=heartbeat)
    except Exception:
        # Verification must never turn an already committed deployment into a
        # failed write or trigger recovery of a successfully installed bundle.
        expected = metadata.get('fingerprint') if isinstance(metadata, dict) else ''
        return report([dict(state='verification-unavailable')], expected or '')


def _verify(targets, metadata, group_id, user_id, *, heartbeat):
    expected = metadata.get('fingerprint') or ''
    endpoints = []
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        return report([dict(state='expected-certificate-unavailable')], expected)
    names = set()
    for index, value in enumerate(metadata.get('domains', [])):
        if index >= MAX_NAMES:
            endpoints.append(dict(state='certificate-name-limit'))
            break
        try:
            names.add('*.' + inventory.domain(value[2:]) if value.startswith('*.') else inventory.domain(value))
        except (ValueError, UnicodeError):
            endpoints.append(dict(state='unsupported-certificate-name'))
    if not names:
        return report(endpoints or [dict(state='no-certificate-names')], expected)
    probes = 0
    for index, (key, target) in enumerate(targets.items()):
        if index >= MAX_TARGETS:
            endpoints.append(dict(state='target-limit'))
            break
        base = dict(server_id=int(key), address=target['address'])
        try:
            heartbeat()
            server = assessments.authorize(int(key), 'haproxy', group_id, user_id, probe=True)
            if server.ip != target['address'] or (target.get('identity') and target['identity'] != dict(
                    ip=server.ip, port=server.port, cred_id=server.cred_id)):
                raise ValueError('Target identity changed')
            if target.get('registration_key') and target['registration_key'] != server.registration_key:
                raise ValueError('Server registration changed')
            before = assessments.identity(server, 'haproxy')
            settings = target['settings']
            if settings.get('cluster_proof', {}).get('mode') == 'passive':
                endpoints.append(dict(base, state='passive-staged'))
                continue
            with group_settings(server.group_id):
                found = inventory.discover(server, 'haproxy')
            selected = found['binding']
            if bool(selected) != bool(settings.get('docker')) or (selected and (
                    selected['name'] != settings.get('container') or
                    selected['runtime'] != containers.validate(settings.get('container_runtime')))):
                raise ValueError('Deployment runtime changed')
            listeners = candidates(found, names)
            if not listeners:
                endpoints.append(dict(base, state='no-discovered-listener'))
                continue
            start = len(endpoints)
            for domain, host, port in listeners:
                if probes >= MAX_PROBES:
                    endpoints.append(dict(base, state='probe-limit'))
                    break
                probes += 1
                heartbeat()
                item = dict(base, domain=domain, port=port)
                try:
                    ip = '::1' if host == '::' else '127.0.0.1' if host in ('*', '0.0.0.0') else host
                    observed = assessments.rpc(server, 'probe', dict(ip=network.address(ip), port=port,
                        domain=domain, tls=True, http=False), binding=selected)
                    fingerprint = observed.get('fingerprint')
                    if fingerprint and not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
                        raise ValueError('Invalid peer fingerprint')
                    item.update(tcp=observed.get('tcp', 'unknown'), tls=observed.get('tls', 'unknown'))
                    if fingerprint:
                        item['fingerprint'] = fingerprint
                    handshaken = item['tcp'] == 'connected' and item['tls'] in ('verified', 'untrusted')
                    item['state'] = ('verified' if handshaken and fingerprint == expected else
                                     'mismatch' if handshaken and fingerprint else
                                     'unreachable' if item['tcp'] != 'connected' else 'handshake-incomplete')
                except Exception:
                    item['state'] = 'listener-unavailable'
                endpoints.append(item)
            with group_settings(server.group_id):
                after = inventory.discover(server, 'haproxy')
            if (after['fingerprint'] != found['fingerprint'] or after['binding'] != selected or
                    assessments.identity(server, 'haproxy') != before):
                for item in endpoints[start:]:
                    item['state'] = 'configuration-changed'
            if not found.get('running_sources_verified'):
                endpoints.append(dict(base, state='running-configuration-unverified'))
        except Exception:
            endpoints.append(dict(base, state='target-unavailable'))
    return report(endpoints, expected)
