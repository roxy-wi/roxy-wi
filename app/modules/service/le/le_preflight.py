"""Persisted setup checks and staging issuance for certificate drafts."""

import json

import dns.resolver

from app.modules.common.time import utc_now
from app.modules.service.le import le_certbot


def check_dns(domain, standalone):
    name = domain.removeprefix('*.')
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5
    if standalone:
        addresses = []
        for kind in ('A', 'AAAA'):
            try:
                addresses.extend(str(record) for record in resolver.resolve(name, kind, search=False))
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                continue
        if not addresses:
            raise le_certbot.CertificateError('No public A/AAAA records were found', 'dns_validation')
    for index in range(len(name.split('.'))):
        parent = '.'.join(name.split('.')[index:])
        try:
            records = list(resolver.resolve(parent, 'CAA', search=False))
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        values = {}
        for record in records:
            tag = record.tag.decode().lower()
            if record.flags & 128 and tag not in ('issue', 'issuewild', 'iodef'):
                raise le_certbot.CertificateError('CAA contains an unsupported critical property', 'caa_denied')
            values.setdefault(tag, []).append(record.value.decode().split(';')[0].strip().lower())
        issuers = values.get('issuewild', values.get('issue', [])) if domain.startswith('*.') else values.get('issue', [])
        if issuers and 'letsencrypt.org' not in issuers:
            raise le_certbot.CertificateError('CAA does not allow letsencrypt.org for this domain', 'caa_denied')
        break
    return 'DNS and CAA checks passed; staging will verify challenge reachability'


def run(state, data, runtime, targets):
    report = {'ok': False, 'revision': state.revision, 'profile_revision': data.get('profile_revision'),
              'checked_at': utc_now().isoformat(), 'checks': []}

    def check(label, operation):
        try:
            detail = operation()
        except Exception as error:
            detail = (error.public_message if isinstance(error, le_certbot.CertificateError) else
                      'Check failed (' + type(error).__name__ + '); verify DNS, SSH and service settings')
            report['checks'].append({'name': label, 'ok': False, 'detail': detail})
        else:
            report['checks'].append({'name': label, 'ok': True, 'detail': detail or 'Passed'})
        state.preflight = json.dumps(report)
        state.save()

    for domain in data['domains']:
        check(domain + ': DNS / CAA', lambda domain=domain: check_dns(domain, data['type'] == 'standalone'))
    for target in targets:
        def server_check(target=target):
            le_certbot.remote(target, dict(le_certbot.deployment_settings(target, state.pem_name),
                                          operation='preflight', standalone=(data['type'] == 'standalone' and target == targets[0])))
            return 'SSH, certificate directory, HAProxy configuration and Runtime API are available'
        check('Server #' + str(target.server_id), server_check)
    if all(item['ok'] for item in report['checks']):
        check('ACME staging', lambda: le_certbot.obtain(data, runtime, targets[0], test=True))
    report['ok'] = all(item['ok'] for item in report['checks'])
    state.preflight = json.dumps(report)
    state.save()
    if not report['ok']:
        raise le_certbot.CertificateError('Setup check failed; see the checks for each domain and server', 'preflight_failed')
