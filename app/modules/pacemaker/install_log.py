"""Persist bounded installation diagnostics in the existing encrypted task payload."""
import json
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.common.time import utc_iso, utc_now
from app.modules.db.db_model import InstallationTasks
from app.modules.operations.queue import serialize_operation_payload
from app.modules.pacemaker.remote import Remote, RemoteError
from app.modules.roxywi.exception import RoxywiPublicError
from app.modules.tools.diagnostics import redact_error


PREFIX = 'ROXYWI_INSTALL_LOG '
MAX_LOG_BYTES = 256000
Record = Callable[[str, str, str, str], None]


class RemoteMessage(BaseModel):
    """Only the installation protocol may contribute remote log messages."""

    model_config = ConfigDict(extra='forbid')
    message: str = Field(max_length=20000)
    level: Literal['info', 'error', 'warning'] = 'info'


def recorder(task: InstallationTasks, payload: dict) -> Record:
    """Keep progress across refreshes without changing the task's queue state."""
    def record(node: str, stage: str, level: str, message: str) -> None:
        entries = payload.setdefault('installation_log', [])
        entries.append(dict(time=utc_iso(utc_now()), node=node, stage=stage, level=level,
                            message=redact_error(message, max_length=16000)))
        while len(json.dumps(entries).encode('utf-8')) > MAX_LOG_BYTES:
            entries.pop(0)
            payload['installation_log_truncated'] = True
        updated = InstallationTasks.update(operation_payload=serialize_operation_payload(payload)).where(
            (InstallationTasks.id == task.id) & (InstallationTasks.operation_id == task.operation_id)).execute()
        if updated != 1:
            raise RoxywiPublicError('Installation task is no longer available; inspect node state before retrying')

    return record


def run(remote: Remote, source: str, node: str, stage: str, record: Record,
        *, data: str | None = None, timeout: int = 90) -> str:
    """Stream explicit diagnostics; never log SSH arguments, stdin or raw stderr."""
    record(node, stage, 'info', 'Started')
    pending = ''
    output = []

    def consume(chunk: str) -> None:
        nonlocal pending
        pending += chunk
        while '\n' in pending:
            line, pending = pending.split('\n', 1)
            if line.startswith(PREFIX):
                event = RemoteMessage.model_validate_json(line[len(PREFIX):])
                record(node, stage, event.level, event.message)
            else:
                output.append(line)

    script = ('INSTALL_LOG = True\ntry:\n    exec(' + repr(source) + ')\n'
              'except SystemExit as exc:\n'
              '    installation_message(str(exc), "error")\n    raise\n'
              'except Exception as exc:\n'
              '    installation_message("Installation step failed: " + type(exc).__name__, "error")\n    raise\n')
    try:
        remote.run(['python3', '-c', script], data=data, timeout=timeout, on_stdout=consume)
        if pending:
            consume('\n')
    except RemoteError as exc:
        record(node, stage, 'error', str(exc).removesuffix('; inspect the node journal'))
        raise RoxywiPublicError(f'Installation failed on {node} during {stage}; open the installation log') from exc
    except Exception as exc:
        record(node, stage, 'error', 'SSH or installation log processing failed: ' + type(exc).__name__)
        raise RoxywiPublicError(f'Installation failed on {node} during {stage}; check SSH access and the installation log') from exc
    record(node, stage, 'info', 'Completed')
    return '\n'.join(output).strip()
