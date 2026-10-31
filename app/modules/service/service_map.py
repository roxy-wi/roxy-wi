"""Configuration-derived publication paths with immutable operator confirmations."""
import json
from pydantic import BaseModel, ConfigDict, Field, field_validator
from peewee import SqliteDatabase, fn
from app.modules.common.time import utc_now, utc_iso
from app.modules.db.db_model import (Server, OperationalAssessment, PublishedServiceConfirmation,
    HaCluster, HaClusterSlave, HaClusterVip, PacemakerCluster)
from app.modules.db import user as user_sql
from app.modules.operations.queue import deserialize_operation_payload as unseal
from app.modules.roxywi.exception import RoxywiConflictError
from app.modules.service import proxy_assessments as assessments, published_endpoints as inventory


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    assessment_id: int = Field(gt=0)
    frontend_id: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=253)
    note: str = Field(min_length=5, max_length=1000)

    @field_validator('domain')
    @classmethod
    def valid_domain(cls, value):
        return inventory.domain(value)


def discover(server, service, heartbeat=lambda: None):
    found = inventory.discover(server, service)
    heartbeat()
    try: addresses = assessments.interfaces(server)
    except Exception: addresses = []
    heartbeat()
    return dict(inventory=found, addresses=addresses, identity=assessments.identity(server, service),
        observed_at=utc_iso(utc_now()), summary='Configuration-derived publication paths; conditional routes remain candidates.')


def latest(group_id):
    # Bounds avoid silently truncating a group-wide view. A failed refresh retains
    # its preceding successful snapshot and is separately visible in pending/history.
    ids = OperationalAssessment.select(fn.MAX(OperationalAssessment.id)).join(Server, on=(
        (OperationalAssessment.server_registration_key == Server.registration_key) &
        (Server.group_id == str(group_id)))).where((OperationalAssessment.group_id == group_id) &
        (OperationalAssessment.kind == 'service-map') & (OperationalAssessment.result != '')).group_by(OperationalAssessment.subject)
    rows = list(OperationalAssessment.select().where(OperationalAssessment.id.in_(ids)).order_by(OperationalAssessment.id.desc()).limit(257))
    if len(rows) > 256: raise ValueError('Service map exceeds 256 proxy bindings; narrow the active group')
    return rows


def confirm(body, group_id, user_id):
    database = OperationalAssessment._meta.database
    with database.atomic('IMMEDIATE') if isinstance(database, SqliteDatabase) else database.atomic():
        row = assessments.get(body.assessment_id, group_id, user_id)
        if not isinstance(database, SqliteDatabase):
            OperationalAssessment.select().where(OperationalAssessment.id == row.id).for_update().get()
        if row.kind != 'service-map' or not row.result: raise ValueError('Select a completed discovery')
        if row.id not in {item.id for item in latest(group_id)}:
            raise RoxywiConflictError('Discovery was superseded; refresh the map before confirming')
        service, ident = row.subject.split(':')
        server = assessments.authorize(int(ident), service, group_id, user_id, probe=True)
        report = unseal(row.result)
        if report['identity'] != assessments.identity(server, service):
            raise RoxywiConflictError('Proxy identity/runtime changed; discover it again')
        if body.frontend_id not in {front['id'] for front in report['inventory']['frontends']}:
            raise ValueError('Select a discovered frontend')
        existing = PublishedServiceConfirmation.get_or_none((PublishedServiceConfirmation.group_id == group_id) &
            (PublishedServiceConfirmation.assessment_id == row.id) & (PublishedServiceConfirmation.frontend_id == body.frontend_id) &
            (PublishedServiceConfirmation.domain == body.domain))
        if existing: return existing
        if PublishedServiceConfirmation.select().where(PublishedServiceConfirmation.assessment_id == row.id).count() >= 1024:
            raise ValueError('This discovery already has 1024 confirmations')
        return PublishedServiceConfirmation.create(group_id=group_id, user_id=user_id, assessment_id=row.id,
            frontend_id=body.frontend_id, domain=body.domain, fingerprint=report['inventory']['fingerprint'], note=body.note)


def ha_dependencies(group_id, user_id, allowed):
    """Read registered topology once per map, regardless of proxy count."""
    if '5' not in user_sql.select_user_services(user_id).split(): return {}
    result = {}
    clusters = list(HaCluster.select().where(HaCluster.group_id == int(group_id)))
    cluster_ids = [cluster.id for cluster in clusters]
    members = {}; vips = {}
    if cluster_ids:
        for item in HaClusterSlave.select().where(HaClusterSlave.cluster_id.in_(cluster_ids)):
            members.setdefault(item.cluster_id_id, set()).add(item.server_id_id)
        for item in HaClusterVip.select().where(HaClusterVip.cluster_id.in_(cluster_ids)):
            vips.setdefault(item.cluster_id_id, []).append(item.vip)
    for cluster in clusters:
        nodes = members.get(cluster.id, set()) & allowed
        dependency = dict(provider='keepalived', id=cluster.id, name=cluster.name, members=sorted(nodes),
            vips=vips.get(cluster.id, []), evidence='registered topology')
        for node in nodes: result.setdefault(node, []).append(dependency)
    for cluster in PacemakerCluster.select().where(PacemakerCluster.group_id == int(group_id)):
        nodes = {int(item['server_id']) for item in json.loads(cluster.servers)} & allowed
        dependency = dict(provider='pacemaker', id=cluster.id, name=cluster.name, members=sorted(nodes),
            vips=[], evidence='registered membership; current resource placement is not inferred')
        for node in nodes: result.setdefault(node, []).append(dependency)
    return result


def view(group_id, user_id, impact_node=None):
    registry = {row.ip: row.server_id for row in Server.select().where(Server.group_id == str(group_id))}
    if impact_node is not None and impact_node not in registry.values(): raise ValueError('Select a registered node in this group')
    rows = []; omitted = 0; topology = None
    from app.modules.db.db_model import ServedTlsMonitor
    from app.modules.service.served_tls import expected,expected_token
    tls_evidence={}
    for monitor in ServedTlsMonitor.select().where(ServedTlsMonitor.group_id==group_id).order_by(ServedTlsMonitor.last_check).limit(256):
        assessment=OperationalAssessment.get_or_none((OperationalAssessment.id==monitor.last_assessment_id)&
            (OperationalAssessment.group_id==group_id)&(OperationalAssessment.kind=='served-tls')&(OperationalAssessment.subject==str(monitor.id)))
        if not assessment or not assessment.result:continue
        observed=unseal(assessment.result)
        try:current=expected_token(expected(unseal(monitor.configuration)['source_id'],group_id))==expected_token(observed['source'])
        except Exception:current=False
        for endpoint in observed['endpoints']:
            if endpoint.get('server_id') and endpoint.get('service'):
                tls_evidence[(endpoint['server_id'],endpoint['service'],observed['domain'],observed['port'])]=dict(
                    monitor_id=monitor.id,observed_at=observed['observed_at'],state=observed['state'],expectation_current=current,
                    tls=endpoint.get('tls','unknown'),fingerprint=endpoint.get('fingerprint'),days_remaining=endpoint.get('days_remaining'))
    for snapshot in latest(group_id):
        service, ident = snapshot.subject.split(':')
        try:
            server = assessments.bound_server(snapshot)
            assessments.authorize(server.server_id, service, group_id, user_id)
        except Exception: omitted += 1; continue
        report = unseal(snapshot.result); found = report['inventory']; identity_current = report['identity'] == assessments.identity(server, service)
        if topology is None: topology = ha_dependencies(group_id, user_id, set(registry.values()))
        dependencies = topology.get(server.server_id, [])
        confirmations = list(PublishedServiceConfirmation.select().where((PublishedServiceConfirmation.group_id == group_id) &
            (PublishedServiceConfirmation.assessment_id == snapshot.id)).order_by(PublishedServiceConfirmation.id).limit(1025))
        if len(confirmations) > 1024: raise ValueError('Too many confirmations for this snapshot')
        by_frontend = {}
        for confirmation in confirmations:
            if confirmation.fingerprint == found['fingerprint']:
                by_frontend.setdefault(confirmation.frontend_id, {})[confirmation.domain] = confirmation
        for front in found['frontends']:
            confirmed = by_frontend.get(front['id'], {})
            domains = sorted(set(front['domains']) | set(confirmed)) or ['']
            impact = {server.server_id: 'proxy host'}
            for dependency in dependencies:
                for node in dependency['members']: impact.setdefault(node, 'HA dependency (failover may preserve service)')
            for backend in front['backends']:
                if backend['host'] in registry: impact.setdefault(registry[backend['host']], 'configured backend candidate')
            if impact_node is not None and impact_node not in impact: continue
            for name in domains:
                confirmation = confirmed.get(name)
                rows.append(dict(assessment_id=snapshot.id, server_id=server.server_id, server=server.hostname, ip=server.ip,
                    service=service, frontend_id=front['id'], frontend=front['name'], domain=name,
                    domain_origin='discovered' if name in front['domains'] else 'operator-supplied' if name else 'unknown',
                    relationship='confirmed' if confirmation else 'discovered',
                    confirmation=dict(id=confirmation.id, user_id=confirmation.user_id, at=utc_iso(confirmation.created_at), note=confirmation.note) if confirmation else None,
                    listeners=front['listeners'], addresses=report['addresses'], backends=front['backends'], tls=front['tls'],
                    ha=dependencies, impact=[dict(server_id=node, reason=reason) for node, reason in sorted(impact.items())],
                    identity_current=identity_current, observed_at=report['observed_at'], fingerprint=found['fingerprint'],
                    partial=found['partial'] or bool(front['unsupported_backends'] or front['not_inventoried']),
                    freshness='last discovery; loaded configuration and active failover are not proven',
                    certificate=[tls_evidence[(server.server_id,service,name,listener['port'])] for listener in front['listeners']
                        if (server.server_id,service,name,listener['port']) in tls_evidence]))
    return dict(data=rows, omitted=omitted, impact_node=impact_node,
        summary='Paths and impact are candidates, not an outage prediction. Confirmations apply only to the displayed snapshot.')
