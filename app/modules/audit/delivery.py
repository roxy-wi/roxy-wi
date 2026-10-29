"""Lease-based, bounded audit export from the existing Scheduler process."""
from datetime import timedelta
import http.client
import json
import os
import re
import secrets
import socket
import ssl
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

from app.modules.audit import destinations
from app.modules.audit.events import write_transaction, locked_state
from app.modules.common.time import utc_now
from app.modules.db.db_model import AuditEvent, AuditDestinationRevision, AuditDelivery, AuditState
from app.modules.integrations.connection_transport import bounded_stream, destination_addresses, http_headers
from app.modules.roxywi.exception import RoxywiPublicError


class ReceiverRejected(RuntimeError):
    def __init__(self, code, permanent=False):
        self.code, self.permanent = code, permanent
        super().__init__(code)


def syslog_message(payload):
    host = re.sub(r'[^A-Za-z0-9_.-]', '_', socket.gethostname())[:255] or '-'
    severity = 4 if payload['outcome'] in {'failed', 'denied', 'unknown'} else 6
    header = f'<{10*8+severity}>1 {payload["timestamp"]} {host} roxy-wi {os.getpid()} audit - '
    return (header+json.dumps(payload, ensure_ascii=True, separators=(',', ':'))).encode('utf-8')


def send(connection, payload):
    settings, credentials = connection.settings, connection.credentials
    deadline = monotonic()+settings['timeout']
    if settings['transport'] == 'https':
        with bounded_stream(settings, credentials, deadline) as stream:
            client = http.client.HTTPConnection(settings['host'], settings['port'], timeout=settings['timeout'])
            client.sock = stream
            try:
                headers = http_headers(settings, credentials)
                headers.update({'Content-Type': 'application/json', 'User-Agent': 'Roxy-WI audit export'})
                client.request('POST', urlsplit(settings['url']).path or '/',
                               body=json.dumps(payload, ensure_ascii=True).encode('utf-8'), headers=headers)
                code = client.getresponse().status
                if not 200 <= code < 300:
                    raise ReceiverRejected(f'HTTP {code}', permanent=400 <= code < 500 and code not in {408, 429})
                return 'receiver_accepted'
            finally:
                client.close()

    message = syslog_message(payload)
    if settings['transport'] == 'udp':
        if len(message) > 8192:
            raise ReceiverRejected('UDP audit message exceeds the 8192-byte limit', permanent=True)
        family, address = destination_addresses(settings['host'], settings['port'])[0]
        with socket.socket(family, socket.SOCK_DGRAM) as stream:
            remaining = deadline-monotonic()
            if remaining <= 0:
                raise TimeoutError('Audit delivery deadline reached')
            stream.settimeout(remaining)
            if stream.sendto(message, address) != len(message):
                raise OSError('Incomplete datagram send')
        return 'datagram_sent'
    with bounded_stream(settings, credentials, deadline) as stream:
        frame = (str(len(message)).encode('ascii')+b' '+message
                 if settings['framing'] == 'octet_counting' else message+b'\n')
        stream.sendall(frame)
        return 'transport_handoff'


def claim():
    now = utc_now()
    eligible = (((AuditDelivery.status == 'pending') & (AuditDelivery.retry_at <= now)) |
                ((AuditDelivery.status == 'sending') & (AuditDelivery.claim_expires_at < now)))
    with write_transaction():
        locked_state()
        row = AuditDelivery.select().where(eligible).order_by(AuditDelivery.id).first()
        if row is None:
            return None
        token = str(uuid4())
        updated = AuditDelivery.update(status='sending', claim_token=token,
                                       claim_expires_at=now+timedelta(minutes=5),
                                       attempts=AuditDelivery.attempts+1).where(
            (AuditDelivery.id == row.id) & eligible).execute()
        if updated != 1:
            return None
        AuditState.update(last_attempt_at=now).where(AuditState.id == 1).execute()
        return AuditDelivery.get_by_id(row.id)


def _finish(row, status, error=None):
    values = dict(status=status, claim_token=None, claim_expires_at=None, last_error=error)
    if status == 'pending':
        delay = min(300, 2**min(row.attempts, 9))+secrets.randbelow(1000)/1000
        values['retry_at'] = utc_now()+timedelta(seconds=delay)
    if status in {'transport_handoff', 'receiver_accepted', 'datagram_sent'}:
        values['handed_off_at'] = utc_now()
    with write_transaction():
        locked_state()
        changed = AuditDelivery.update(**values).where(
            (AuditDelivery.id == row.id) & (AuditDelivery.claim_token == row.claim_token) &
            (AuditDelivery.status == 'sending')).execute()
        if changed:
            state = {'last_error': error}
            if values.get('handed_off_at'):
                state['last_handoff_at'] = values['handed_off_at']
            AuditState.update(**state).where(AuditState.id == 1).execute()
        return bool(changed)


def process(limit=20, time_budget=20):
    deadline = monotonic()+time_budget
    processed = 0
    while processed < limit and monotonic() < deadline:
        row = claim()
        if row is None:
            break
        try:
            revision = AuditDestinationRevision.get_by_id(row.destination_revision_id)
            event = AuditEvent.get_by_id(row.event_id)
            result = send(destinations.resolve_revision(revision), json.loads(event.payload))
        except ReceiverRejected as error:
            _finish(row, 'failed' if error.permanent else 'pending', error.code)
        except RoxywiPublicError:
            _finish(row, 'failed', 'Pinned connection profile is unavailable or disabled')
        except ssl.SSLCertVerificationError:
            _finish(row, 'failed', 'TLS certificate verification failed; inspect receiver trust settings')
        except (OSError, http.client.HTTPException, TimeoutError):
            # Error strings may contain receiver-controlled or sensitive data.
            _finish(row, 'pending', 'Connection or TLS delivery failed')
        except Exception:
            _finish(row, 'failed', 'Audit payload or receiver configuration is unavailable')
        else:
            _finish(row, result)
        processed += 1
    return processed
