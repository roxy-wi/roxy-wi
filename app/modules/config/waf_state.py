"""Track Roxy-WI writes and confirmed WAF applies, not external file changes.

As with rule creation, workers serialize operations using shared lib storage.
Reserve a revision before remote I/O: lost SSH replies and worker exits must
leave an unconfirmed change, never a stale successful-apply indication.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
from uuid import uuid4

from app.modules.common.file_lock import file_lock
from app.modules.common.time import utc_now
from app.modules.db.db_model import WafConfigState
from app.modules.roxy_wi_tools import GetConfigVar


def operation_lock(server_ip: str, service: str):
    lock_id = hashlib.sha256(f'{server_ip}\0{service}'.encode('utf-8')).hexdigest()
    lock_dir = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'waf-locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    return file_lock(lock_dir / f'{lock_id}.lock')


def status(server_id: int, service: str) -> str:
    row = WafConfigState.get_or_none(WafConfigState.server == server_id, WafConfigState.service == service)
    if row is None:
        return 'unknown'
    return 'applied' if row.revision == row.applied_revision else 'pending'


@contextmanager
def track_changes(server_id: int, service: str, *, applying=False):
    """Caller holds operation_lock through the remote operation and confirmation."""
    if service not in ('haproxy', 'nginx'):
        raise ValueError('Unsupported WAF service')
    revision = uuid4().hex
    row, _ = WafConfigState.get_or_create(server=server_id, service=service, defaults={'revision': revision})
    WafConfigState.update(revision=revision).where(WafConfigState.id == row.id).execute()
    yield
    if applying:
        updated = WafConfigState.update(applied_revision=revision, applied_at=utc_now()).where(
            WafConfigState.id == row.id, WafConfigState.revision == revision).execute()
        if not updated:
            raise RuntimeError('WAF configuration changed during apply confirmation')
