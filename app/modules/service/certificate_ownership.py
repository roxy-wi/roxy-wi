"""Serialize automatic certificate owners across providers and Let's Encrypt."""
from peewee import SqliteDatabase

from app.modules.db.db_model import CertificateSource, LetsEncrypt, LetsEncryptState, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.roxywi.exception import RoxywiConflictError
from app.modules.service.certificates import targets_for


def current(query):
    return query if isinstance(query.model._meta.database, SqliteDatabase) else query.for_update()


def check(ids, pem_name, group_id, *, source_id=None, le_id=None):
    """Call in an IMMEDIATE SQLite / ordinary MySQL transaction before saving."""
    ids = set(ids)
    list(current(Server.select().where(Server.server_id.in_(ids)).order_by(Server.server_id)))
    for row in current(CertificateSource.select().where(CertificateSource.group_id == group_id)):
        if row.id == source_id:
            continue
        data = deserialize_operation_payload(row.configuration)
        if data['pem_name'] != pem_name:
            continue
        other = targets_for(data['server_id'], group_id, cluster_id=data.get('cluster_id'))
        if ids & {server.server_id for server in other}:
            raise RoxywiConflictError('Another certificate source already owns this PEM on a target')
    for state in current(LetsEncryptState.select().where(LetsEncryptState.pem_name == pem_name)):
        if state.le_id == le_id or state.status == 'deleted':
            continue
        row = LetsEncrypt.get_or_none(LetsEncrypt.id == state.le_id)
        if row is None:
            continue
        other_ids = {row.server_id_id}
        if state.pending_config:
            other_ids.add(deserialize_operation_payload(state.pending_config)['server_id'])
        other_ids |= {s.server_id for s in Server.select().where(Server.master.in_(other_ids))}
        if ids & other_ids:
            raise RoxywiConflictError("A Let's Encrypt schedule already owns this PEM on a target")
