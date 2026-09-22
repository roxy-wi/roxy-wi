"""Renewal decisions for imported PEMs that have no managed Certbot lineage yet."""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from app.modules.roxywi import logger


def due(bundle, root, proxies=None, now=None):
    now = now or datetime.now(timezone.utc)
    certificate = x509.load_pem_x509_certificate(bundle['fullchain'].encode())
    if now >= certificate.not_valid_after_utc:
        return True  # RFC 9773 forbids ARI requests for expired certificates.
    lifetime = certificate.not_valid_after_utc - certificate.not_valid_before_utc
    fallback = certificate.not_valid_before_utc + lifetime * (0.5 if lifetime.days < 10 else 2 / 3)
    cache = root / 'imported-ari.json'
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
    saved = {}
    if cache.exists():
        try:
            saved = json.loads(cache.read_text())
            if saved['fingerprint'] != fingerprint:
                saved = {}
            else:
                for field in ('check_after', 'renew_at'):
                    if datetime.fromisoformat(saved[field]).tzinfo is None:
                        raise ValueError('ARI cache timestamps must have a timezone')
        except (ValueError, KeyError, TypeError):
            logger.warning('Imported LE certificate ARI cache is invalid; refreshing renewal information')
            saved = {}
    if not saved or datetime.fromisoformat(saved['check_after']) <= now:
        saved = {'fingerprint': fingerprint, 'check_after': (now + timedelta(hours=6)).isoformat(),
                 'renew_at': saved.get('renew_at', fallback.isoformat())}
        try:
            key_id = certificate.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier
            serial = certificate.serial_number.to_bytes((certificate.serial_number.bit_length() + 7) // 8, 'big')
            if serial[0] & 0x80:
                serial = b'\x00' + serial  # DER INTEGER must remain positive (RFC 9773 §4.1).
            encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
            identity = encode(key_id) + '.' + encode(serial)
            with requests.get('https://acme-v02.api.letsencrypt.org/directory', proxies=proxies, timeout=(5, 15)) as response:
                response.raise_for_status()
                endpoint = response.json()['renewalInfo']
            with requests.get(endpoint.rstrip('/') + '/' + identity, proxies=proxies, timeout=(5, 15)) as response:
                response.raise_for_status()
                window = response.json()['suggestedWindow']
                start = datetime.fromisoformat(window['start'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(window['end'].replace('Z', '+00:00'))
                if start.tzinfo is None or end.tzinfo is None or end <= start:
                    raise ValueError('Invalid ARI window')
                fraction = int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16) / 0xffffffff
                saved['renew_at'] = (start + (end - start) * fraction).isoformat()
                retry = response.headers.get('Retry-After', '')
                if retry:
                    retry_at = now + timedelta(seconds=int(retry)) if retry.isdigit() else parsedate_to_datetime(retry)
                    saved['check_after'] = max(now + timedelta(minutes=1), retry_at).isoformat()
        except (requests.RequestException, ValueError, KeyError, TypeError, x509.ExtensionNotFound) as error:
            logger.warning('Imported LE certificate ARI unavailable (' + type(error).__name__ + '); keeping the saved or lifetime-based renewal time')
        from app.modules.service.le.le_certbot import private_write
        private_write(cache, json.dumps(saved))
    # Renew in this run if the chosen time would pass before the next scheduled check.
    return now + timedelta(hours=12) >= datetime.fromisoformat(saved['renew_at'])
