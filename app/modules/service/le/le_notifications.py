"""Transactional, deduplicated LE alerts delivered by the notification outbox."""

import json
from datetime import timedelta
from uuid import uuid4

from app.modules.common.time import utc_now
from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, ServiceNotification, Server
from app.modules.service.le.le_store import transaction, locked


def check_notifications(now=None):
    now = now or utc_now()
    queued = 0
    candidates = LetsEncryptState.select(LetsEncryptState.id).where(
        (LetsEncryptState.legacy_pending == False) & (LetsEncryptState.status != 'deleted') &
        (LetsEncryptState.draft == False))
    for candidate in candidates:
        with transaction():
            state = locked(LetsEncryptState, LetsEncryptState.id == candidate.id)
            row = LetsEncrypt.get_or_none(LetsEncrypt.id == state.le_id)
            server = Server.get_or_none(Server.server_id == row.server_id_id) if row else None
            if not server:
                continue
            sent = json.loads(state.notification_state)

            def notify(level, message):
                nonlocal queued
                ServiceNotification.create(event_id=str(uuid4()), category='letsencrypt', observed_at=now,
                    payload=json.dumps({'service': 'letsencrypt', 'server_address': server.ip,
                                        'group_id': int(server.group_id), 'level': level,
                                        'message': "Let's Encrypt #" + str(state.le_id) + ': ' + message,
                                        'alert_type': 'service'}))
                queued += 1

            failed = state.failures >= 3 or any(target.get('status') == 'rollback_failed'
                                               for target in json.loads(state.targets).values())
            if failed and not sent.get('failure'):
                notify('critical', 'Certificate operation needs attention. ' + (state.last_error or ''))
                sent['failure'] = True
            elif state.status == 'active' and sent.get('failure'):
                notify('info', 'Certificate issuance and deployment recovered')
                sent['failure'] = False
            if state.not_after:
                remaining = (state.not_after - now).total_seconds() / 86400
                threshold = next((days for days in (0, 1, 3, 7, 14) if remaining <= days), None)
                identity = str(state.fingerprint) + ':' + str(threshold)
                if threshold is not None and sent.get('expiry') != identity:
                    notify('critical' if threshold <= 3 else 'warning',
                           'Certificate expires at ' + state.not_after.isoformat() + 'Z')
                    sent['expiry'] = identity
            state.notification_state = json.dumps(sent)
            state.save()
    ServiceNotification.delete().where((ServiceNotification.category == 'letsencrypt') &
        ServiceNotification.status.in_(('delivered', 'cancelled')) &
        (ServiceNotification.updated_at < now - timedelta(days=30))).execute()
    return queued
