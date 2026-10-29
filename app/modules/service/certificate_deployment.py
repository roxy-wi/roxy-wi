"""Shared, journaled multi-target deployment for every certificate source.

Callers own issuance/retrieval and their database commit boundary. This module
owns the remote apply/finalize loops; persist must durably record each step.
"""
from app.modules.service.certificates import CertificateError


def apply(targets, bundle, name, transaction, *, resolve, deploy, persist, renew=None):
    for key, target in targets.items():
        if target.get('status') == 'applied':
            continue
        if renew:
            renew()
        server = resolve(key, target)
        target.update(status='applying', started=True)
        persist()
        try:
            result = deploy(server, bundle, name, settings=target['settings'], transaction=transaction)
        except Exception as error:
            target.update(status='failed', error_code=getattr(error, 'code', 'operation_failed'))
            persist()
            raise
        target.update(status='applied')
        target.pop('error_code', None)
        if isinstance(result,dict) and result.get('verification'):
            target['verification'] = result['verification']
        persist()


def finish(targets, phase, transaction, *, resolve, remote, persist, renew=None):
    if phase not in ('commit', 'rollback'):
        raise ValueError('Invalid certificate deployment phase')
    failures = []
    for key, target in targets.items():
        if not target.get('started') or target.get('finished') == phase:
            continue
        try:
            if renew:
                renew()
            server = resolve(key, target)
            result=remote(server, dict(target['settings'], operation=phase, transaction=transaction))
            if isinstance(result,dict) and result.get('verification'):target['verification']=result['verification']
            target.update(finished=phase, status='rolled_back' if phase == 'rollback' else 'applied')
            target.pop('error_code', None)
        except Exception as error:
            target.update(status='failed', error_code=getattr(error, 'code', 'recovery_failed'))
            failures.append(key)
        persist()
    if failures:
        raise CertificateError('Certificate ' + phase + ' incomplete on servers ' + ', '.join(failures), 'recovery_failed')
