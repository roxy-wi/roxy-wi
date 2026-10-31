from functools import wraps

from flask import abort, g, jsonify, render_template, request, redirect, url_for
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from app.middleware import get_user_params
from app.modules.db.db_model import PacemakerCluster, PacemakerChange, PacemakerEvent, InstallationTasks, Server
from app.modules.pacemaker import service, operations, monitor
from app.modules.pacemaker.bootstrap import corosync_config
from app.modules.pacemaker.remote import RemoteError
from app.modules.pacemaker.schemas import ClusterCreate, Candidate, Action, Bootstrap, CorosyncCandidate, Discovery, Adoption, WitnessInstall, WitnessMigration, WitnessRecovery
from app.modules.pacemaker.editor import Edit, Resource, build
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiInputError, RoxywiConflictError, RoxywiResourceNotFound, RoxywiValidationError
from app.routes.pacemaker import bp
from app.modules.service.ha_topology import topology_lock


@bp.before_request
@jwt_required()
@get_user_params()
def before_request():
    if not auth.is_access_permit_to_service('cluster'):
        abort(403)
    if request.method != 'GET' and int(g.user_params['role']) > 3:
        abort(403)


def api(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except HTTPException:
            raise
        except RoxywiResourceNotFound as exc:
            return jsonify(error=exc.public_message), 404
        except RoxywiConflictError as exc:
            return jsonify(error=exc.public_message), 409
        except ValidationError:
            return jsonify(error='Invalid fields; check names, addresses and required values'), 400
        except RoxywiValidationError as exc:
            return jsonify(error=exc.public_message), 400
        except RoxywiInputError as exc:
            return jsonify(error=exc.public_message), 400
        except ValueError:
            return jsonify(error='Invalid value provided; check the request fields'), 400
        except RemoteError:
            return jsonify(error='Cluster command failed; inspect application and node logs'), 502
        except Exception:
            return jsonify(error='Cluster operation failed; inspect application and node logs'), 502
    return wrapped


def current(cluster_id):
    return service.get_cluster(cluster_id, g.user_params['group_id'])


def operator():
    if int(g.user_params['role']) > 3:
        abort(403)


def queued(cluster, action, data=None):
    task = operations.enqueue(cluster, g.user_params['user_id'], action, data)
    return jsonify(task_id=task.id, status=task.status), 202


@bp.get('')
def index():
    mode = request.args.get('setup')
    if mode in ('new', 'adopt', 'witness'):
        return redirect(url_for('ha.cluster_index', setup=mode, cluster=request.args.get('cluster', type=int)))
    return render_template('pacemaker.html', lang=g.user_params['lang'], view='overview')


@bp.get('/<any(resources,configuration,quorum,logs,monitoring,history):view>')
def page(view):
    if view in ('configuration', 'quorum', 'logs', 'monitoring'):
        operator()
    return render_template('pacemaker.html', lang=g.user_params['lang'], view=view)


@bp.get('/api')
@api
def clusters():
    rows = PacemakerCluster.select().where(PacemakerCluster.group_id == g.user_params['group_id'])
    return jsonify(data=[service.serialize(row) for row in rows])


@bp.get('/api/servers')
@api
def servers():
    rows = Server.select().where((Server.group_id == g.user_params['group_id']) &
                                 (Server.enabled == 1) & (Server.type_ip == 0))
    return jsonify(data=[{'id': row.server_id, 'name': row.hostname, 'ip': row.ip} for row in rows])


@bp.get('/api/servers/<int:server_id>/facts')
@api
def server_facts(server_id):
    operator()
    from app.modules.pacemaker.facts import read
    return jsonify(data=read(server_id, g.user_params['group_id']))


@bp.get('/api/<int:cluster_id>/agents')
@api
def agents(cluster_id):
    operator()
    from app.modules.pacemaker.agents import inventory
    return jsonify(data=inventory(current(cluster_id)))


@bp.get('/api/<int:cluster_id>/agents/metadata')
@api
def agent_metadata(cluster_id):
    operator()
    from app.modules.pacemaker.agents import AgentRequest, metadata
    body = AgentRequest(agent=request.args.get('agent', ''))
    return jsonify(data=metadata(current(cluster_id), body.agent))


@bp.get('/api/<int:cluster_id>/agents/packages')
@api
def agent_packages(cluster_id):
    operator()
    from app.modules.pacemaker.agents import packages
    return jsonify(data=packages(current(cluster_id)))


@bp.post('/api/<int:cluster_id>/agents/packages')
@api
def agent_package_install(cluster_id):
    from app.modules.pacemaker.agents import PackageRequest, plan
    cluster = current(cluster_id)
    body = PackageRequest.model_validate(request.get_json())
    if body.confirm != cluster.name:
        raise RoxywiInputError('Confirm the cluster name before installing packages')
    plan(cluster, body.package, body.plan_digest)
    return queued(cluster, 'agent-install', {'package': body.package, 'plan_digest': body.plan_digest})


@bp.post('/api/<int:cluster_id>/agents/repositories')
@api
def agent_repositories(cluster_id):
    from app.modules.pacemaker.schemas import StrictModel
    class Confirm(StrictModel):
        confirm: str
    cluster = current(cluster_id)
    if Confirm.model_validate(request.get_json()).confirm != cluster.name:
        raise RoxywiInputError('Confirm the cluster name before refreshing repositories')
    return queued(cluster, 'agent-repositories')


@bp.get('/api/<int:cluster_id>/choices')
@api
def resource_choices(cluster_id):
    operator()
    from app.modules.pacemaker.xml import configuration
    cluster = current(cluster_id)
    config = configuration(service.get_config(cluster)['xml'])
    resources = [{'id': item.get('id'), 'type': item.tag} for item in config.findall('./resources//*')
                 if item.tag in ('primitive', 'group', 'clone', 'master', 'bundle') and item.get('id')]
    constraints = [{'id': item.get('id'), 'type': item.tag} for item in config.findall('./constraints/*') if item.get('id')]
    return jsonify(data={'resources': resources, 'constraints': constraints,
                         'nodes': [member.name for member, _server in service.members(cluster)]})


@bp.post('/api')
@api
def create():
    row = service.register(ClusterCreate.model_validate(request.get_json()), g.user_params['group_id'])
    service.event(row, g.user_params['user_id'], 'register', 'completed')
    return jsonify(data=service.serialize(row)), 201


@bp.post('/api/discover')
@api
def discover():
    from app.modules.pacemaker.adoption import discover as discover_cluster
    body = Discovery.model_validate(request.get_json())
    return jsonify(data=discover_cluster(body.server_id, g.user_params['group_id']))


@bp.post('/api/witness/install')
@api
def witness_install():
    body = WitnessInstall.model_validate(request.get_json())
    task = operations.enqueue_witness(body.server_id, g.user_params['group_id'], g.user_params['user_id'], docker=body.docker,
        **({'container_engine':body.container_engine} if body.container_engine is not None else {}))
    return jsonify(task_id=task.id, status=task.status), 202


@bp.get('/api/witness/<int:server_id>/logs')
@api
def witness_logs(server_id):
    operator()
    from app.modules.pacemaker.qdevice import witness_server
    from app.modules.pacemaker.remote import Remote
    from app.modules.pacemaker.witness_docker import RUNTIME
    source=RUNTIME+"\nstate=container_state()\nargs=[ENGINE,'logs','--tail','100',CONTAINER] if state else ['journalctl','--unit=corosync-qnetd','--no-pager','-n','100']\nresult=subprocess.run(args,capture_output=True,text=True,timeout=30,check=True)\nprint(result.stdout+result.stderr)\n"
    server=witness_server(server_id,g.user_params['group_id'])
    return jsonify(data=Remote(server).run(['python3','-c',source]))


@bp.get('/api/witness/<int:server_id>/migration')
@api
def witness_migration_plan(server_id):
    operator()
    from app.modules.pacemaker.witness_migration import plan
    return jsonify(data=plan(server_id,g.user_params['group_id'],container_engine=request.args.get('container_engine','docker')))


@bp.post('/api/witness/<int:server_id>/migration')
@api
def witness_migrate(server_id):
    from app.modules.pacemaker.witness_migration import plan
    body=WitnessMigration.model_validate(request.get_json())
    current_plan=plan(server_id,g.user_params['group_id'],container_engine=body.container_engine)
    if body.confirm!=current_plan['server']: raise RoxywiInputError('Type the witness server name to confirm migration')
    if not current_plan.get('eligible') or body.plan_digest!=current_plan['plan_digest']:
        raise RoxywiConflictError('Migration plan changed; review again')
    task=operations.enqueue_witness(server_id,g.user_params['group_id'],g.user_params['user_id'],
        action='witness-migrate',data={'plan_digest':body.plan_digest,'container_engine':body.container_engine})
    return jsonify(task_id=task.id,status=task.status),202


@bp.post('/api/witness/<int:server_id>/migration/recover')
@api
def witness_recover(server_id):
    from app.modules.pacemaker.qdevice import witness_server
    body=WitnessRecovery.model_validate(request.get_json())
    server=witness_server(server_id,g.user_params['group_id'])
    if body.confirm!=server.hostname: raise RoxywiInputError('Type the witness server name to confirm recovery')
    task=operations.enqueue_witness(server_id,g.user_params['group_id'],g.user_params['user_id'],
        action='witness-recover',data={'token':body.token})
    return jsonify(task_id=task.id,status=task.status),202


@bp.get('/api/witness/<int:server_id>/lifecycle/<any(native,"image-upgrade"):operation>')
@api
def witness_lifecycle_plan(server_id,operation):
    operator()
    from app.modules.pacemaker.witness_lifecycle import plan
    return jsonify(data=plan(server_id,g.user_params['group_id'],operation))


@bp.post('/api/witness/<int:server_id>/lifecycle/<any(native,"image-upgrade"):operation>')
@api
def witness_lifecycle_start(server_id,operation):
    from app.modules.pacemaker.witness_lifecycle import plan
    body=WitnessMigration.model_validate(request.get_json())
    current_plan=plan(server_id,g.user_params['group_id'],operation)
    if body.confirm!=current_plan['server']:raise RoxywiInputError('Type the witness server name to confirm the operation')
    if not current_plan.get('eligible') or body.plan_digest!=current_plan['plan_digest']:raise RoxywiConflictError('Witness plan changed; review again')
    task=operations.enqueue_witness(server_id,g.user_params['group_id'],g.user_params['user_id'],action='witness-lifecycle',data=dict(operation=operation,plan_digest=body.plan_digest))
    return jsonify(task_id=task.id,status=task.status),202


@bp.post('/api/witness/<int:server_id>/lifecycle/recover')
@api
def witness_lifecycle_recover(server_id):
    from app.modules.pacemaker.qdevice import witness_server
    body=WitnessRecovery.model_validate(request.get_json());server=witness_server(server_id,g.user_params['group_id'])
    if body.confirm!=server.hostname:raise RoxywiInputError('Type the witness server name to confirm recovery')
    task=operations.enqueue_witness(server_id,g.user_params['group_id'],g.user_params['user_id'],action='witness-lifecycle-recover',data=dict(token=body.token))
    return jsonify(task_id=task.id,status=task.status),202


@bp.get('/api/witness/<int:server_id>/trust/<int:target_id>')
@api
def witness_trust_plan(server_id,target_id):
    operator()
    from app.modules.pacemaker.witness_trust import plan
    return jsonify(data=plan(server_id,target_id,g.user_params['group_id'],request.args.get('rotate')=='1'))


@bp.post('/api/witness/<int:server_id>/trust')
@api
def witness_trust_start(server_id):
    from app.modules.pacemaker.schemas import WitnessTrust
    from app.modules.pacemaker.witness_trust import plan
    body=WitnessTrust.model_validate(request.get_json())
    reviewed=plan(server_id,body.target_id,g.user_params['group_id'],body.rotate_ca)
    if body.confirm!=reviewed['server']:raise RoxywiInputError('Type the source witness name to confirm the trust change')
    if not reviewed.get('eligible') or body.plan_digest!=reviewed['plan_digest']:raise RoxywiConflictError('Trust plan changed; review again')
    task=operations.enqueue_witness(server_id,g.user_params['group_id'],g.user_params['user_id'],action='witness-trust',data=body.model_dump())
    return jsonify(task_id=task.id,status=task.status),202


@bp.post('/api/witness/<int:server_id>/trust/recover')
@api
def witness_trust_recover(server_id):
    from app.modules.pacemaker.qdevice import witness_server
    body=WitnessRecovery.model_validate(request.get_json());server=witness_server(server_id,g.user_params['group_id'])
    if body.confirm!=server.hostname:raise RoxywiInputError('Type the source witness name to confirm recovery')
    task=operations.enqueue_witness(server_id,g.user_params['group_id'],g.user_params['user_id'],action='witness-trust-recover',data=dict(token=body.token))
    return jsonify(task_id=task.id,status=task.status),202


@bp.get('/api/platform/<int:server_id>')
@api
def platform(server_id):
    operator()
    from app.modules.pacemaker.adoption import server_for
    from app.modules.pacemaker.platforms import DETECT
    from app.modules.pacemaker.remote import Remote
    import json
    server = server_for(server_id, g.user_params['group_id'])
    return jsonify(data=json.loads(Remote(server).run(['python3', '-c', DETECT])))


@bp.get('/api/witness/<int:server_id>')
@api
def witness_status(server_id):
    operator()
    from app.modules.pacemaker.qdevice import witness_status as read_status
    return jsonify(data=read_status(server_id, g.user_params['group_id']))


@bp.get('/api/witness/tasks/<int:task_id>')
@api
def witness_task(task_id):
    operator()
    row = InstallationTasks.get_or_none((InstallationTasks.id == task_id) &
        (InstallationTasks.group_id == g.user_params['group_id']) & (InstallationTasks.operation_type == 'pacemaker'))
    if not row:
        abort(404)
    from app.modules.operations.queue import deserialize_operation_payload
    if deserialize_operation_payload(row.operation_payload).get('action') not in ('witness-install','witness-migrate','witness-recover','witness-lifecycle','witness-lifecycle-recover','witness-trust','witness-trust-recover'):
        abort(404)
    return jsonify(data={'id': row.id, 'status': row.status, 'error': row.error,
                         'result':deserialize_operation_payload(row.operation_payload).get('result')})


@bp.post('/api/adopt')
@api
def adopt():
    from app.modules.pacemaker.adoption import adopt as adopt_cluster
    body = Adoption.model_validate(request.get_json())
    cluster = adopt_cluster(body, g.user_params['group_id'], g.user_params['user_id'])
    return jsonify(data=service.serialize(cluster)), 201


@bp.put('/api/<int:cluster_id>/monitor')
@api
def monitoring(cluster_id):
    cluster = current(cluster_id)
    body = request.get_json()
    if not isinstance(body, dict) or set(body) != {'enabled'} or type(body['enabled']) is not bool:
        raise RoxywiInputError('enabled must be a boolean')
    PacemakerCluster.update(monitor_enabled=body['enabled']).where(PacemakerCluster.id == cluster.id).execute()
    service.event(cluster, g.user_params['user_id'], 'monitoring', 'enabled' if body['enabled'] else 'disabled')
    return jsonify(status='saved')


@bp.delete('/api/<int:cluster_id>')
@api
def remove(cluster_id):
    cluster = current(cluster_id)
    with topology_lock(), service.locked(cluster):
        cluster = current(cluster_id)
        if cluster.active_task_id:
            raise RoxywiConflictError('Wait for the current operation before removing this registration')
        # Unregister only; deleting infrastructure must remain an explicit host operation.
        cluster.delete_instance(recursive=True)
    return jsonify(status='unregistered')


@bp.get('/api/<int:cluster_id>/status')
@api
def status(cluster_id):
    state = service.status(current(cluster_id))
    return jsonify(data=state, health=monitor.health(state))


@bp.get('/api/<int:cluster_id>/config')
@api
def config(cluster_id):
    operator()
    return jsonify(data=service.get_config(current(cluster_id)))


@bp.get('/api/<int:cluster_id>/transport')
@api
def transport_plan(cluster_id):
    operator()
    from app.modules.pacemaker.transport import plan
    token=request.args.get('token',1500,type=int)
    if not 1000<=token<=30000:raise RoxywiInputError('Token timeout must be between 1000 and 30000 ms')
    return jsonify(data=plan(current(cluster_id),token))


@bp.post('/api/<int:cluster_id>/transport')
@api
def transport_migrate(cluster_id):
    from app.modules.pacemaker.schemas import TransportMigration
    from app.modules.pacemaker.transport import plan
    cluster=current(cluster_id);body=TransportMigration.model_validate(request.get_json())
    if body.confirm!=cluster.name:raise RoxywiInputError('Type the cluster name to confirm planned transport downtime')
    reviewed=plan(cluster,body.token)
    if not reviewed.get('eligible') or reviewed['plan_digest']!=body.plan_digest:raise RoxywiConflictError('Transport plan changed; review it again')
    return queued(cluster,'transport-migrate',body.model_dump())


@bp.post('/api/<int:cluster_id>/transport/<any(quiesce,resume,recover):operation>')
@api
def transport_control(cluster_id,operation):
    from app.modules.pacemaker.schemas import ClusterConfirmation
    cluster=current(cluster_id);body=ClusterConfirmation.model_validate(request.get_json())
    if body.confirm!=cluster.name:raise RoxywiInputError('Type the cluster name to confirm transport maintenance')
    return queued(cluster,'transport-'+operation,body.model_dump())


@bp.get('/api/<int:cluster_id>/autostart')
@api
def autostart_status(cluster_id):
    operator()
    from app.modules.pacemaker.autostart import status
    return jsonify(data=status(current(cluster_id)))


@bp.post('/api/<int:cluster_id>/autostart')
@api
def autostart_policy(cluster_id):
    from app.modules.pacemaker.autostart import Policy
    cluster=current(cluster_id);body=Policy.model_validate(request.get_json())
    if body.confirm!=cluster.name:raise RoxywiInputError('Type the cluster name to confirm')
    return queued(cluster,'autostart-policy',body.model_dump())


@bp.get('/api/<int:cluster_id>/corosync')
@api
def corosync(cluster_id):
    operator()
    cluster = current(cluster_id)
    result = []
    for member, server in service.members(cluster):
        from app.modules.pacemaker.remote import Remote
        remote = Remote(server)
        result.append({'node': member.name, 'config': remote.run(['cat', '/etc/corosync/corosync.conf']),
                       'quorum': remote.run(['corosync-quorumtool', '-s'], allowed=(0, 2))})
    return jsonify(data=result)


@bp.get('/api/<int:cluster_id>/corosync-template')
@api
def corosync_template(cluster_id):
    operator()
    cluster = current(cluster_id)
    return jsonify(data=corosync_config(cluster, service.members(cluster)))


@bp.post('/api/<int:cluster_id>/corosync')
@api
def corosync_draft(cluster_id):
    from app.modules.pacemaker.corosync import draft
    body = CorosyncCandidate.model_validate(request.get_json())
    change = draft(current(cluster_id), g.user_params['user_id'], body)
    return jsonify(id=change.id, status=change.status), 201


@bp.post('/api/<int:cluster_id>/bootstrap')
@api
def bootstrap(cluster_id):
    cluster = current(cluster_id)
    body = Bootstrap.model_validate(request.get_json())
    if body.confirm != cluster.name:
        raise RoxywiInputError('Confirm the cluster name before provisioning')
    return queued(cluster, 'bootstrap', {'syn_flood': body.syn_flood, 'fence_pve': body.fence_pve})


@bp.post('/api/<int:cluster_id>/actions')
@api
def action(cluster_id):
    body = Action.model_validate(request.get_json())
    return queued(current(cluster_id), 'operate', body.model_dump())


@bp.post('/api/<int:cluster_id>/changes')
@api
def draft(cluster_id):
    body = Candidate.model_validate(request.get_json())
    change = service.draft(current(cluster_id), g.user_params['user_id'], body)
    return jsonify(id=change.id, status=change.status), 201


@bp.post('/api/<int:cluster_id>/build')
@api
def build_change(cluster_id):
    cluster = current(cluster_id)
    body = Edit.model_validate(request.get_json())
    if body.kind == 'resource':
        from app.modules.pacemaker.agents import validate_resource
        validate_resource(cluster, Resource.model_validate(body.data))
    live = service.get_config(cluster)
    if live['digest'] != body.base_digest:
        raise RoxywiConflictError('Configuration changed; refresh before creating a new change')
    candidate = build(live['xml'], body)
    change = service.draft(cluster, g.user_params['user_id'], candidate)
    return jsonify(id=change.id, status=change.status), 201


@bp.post('/api/<int:cluster_id>/changes/<int:change_id>/<action>')
@api
def change_action(cluster_id, change_id, action):
    cluster = current(cluster_id)
    service.change_for(cluster, change_id)
    if action == 'restore':
        change = service.restore_draft(cluster, change_id, g.user_params['user_id'])
        return jsonify(id=change.id, status=change.status), 201
    if action not in ('validate', 'apply'):
        abort(404)
    return queued(cluster, action, {'change_id': change_id})


@bp.get('/api/<int:cluster_id>/changes/<int:change_id>')
@api
def get_change(cluster_id, change_id):
    operator()
    change = service.change_for(current(cluster_id), change_id)
    return jsonify(data={'id': change.id, 'status': change.status,
                         'kind': change.kind,
                         'base_digest': change.base_digest,
                         'xml': service.decrypt(change.candidate), 'previous': service.decrypt(change.previous),
                         'result': service.decrypt(change.result) if change.result else None})


@bp.get('/api/<int:cluster_id>/history')
@api
def history(cluster_id):
    cluster = current(cluster_id)
    events = PacemakerEvent.select().where(PacemakerEvent.cluster == cluster.id).order_by(PacemakerEvent.id.desc()).limit(100)
    changes = PacemakerChange.select().where(PacemakerChange.cluster == cluster.id).order_by(PacemakerChange.id.desc()).limit(50)
    task = InstallationTasks.get_or_none(InstallationTasks.id == cluster.active_task_id) if cluster.active_task_id else None
    installations = []
    if int(g.user_params['role']) <= 3:
        installations = [{'id': row.id, 'status': row.status, 'date': row.start_date.isoformat()}
                         for row in service.installation_history(cluster)]
    return jsonify(events=[{'id': row.id, 'user_id': row.user_id, 'date': row.created_at.isoformat(),
                            'action': row.action, 'status': row.status} for row in events],
                   changes=[{'id': row.id, 'kind': row.kind, 'status': row.status, 'date': row.created_at.isoformat()} for row in changes],
                   task={'id': task.id, 'status': task.status} if task else None, installations=installations)


@bp.get('/api/<int:cluster_id>/tasks/<int:task_id>')
@api
def task(cluster_id, task_id):
    cluster = current(cluster_id)
    row = InstallationTasks.get_or_none((InstallationTasks.id == task_id) &
                                        (InstallationTasks.group_id == cluster.group_id) &
                                        (InstallationTasks.operation_type == 'pacemaker'))
    if not row:
        abort(404)
    from app.modules.operations.queue import deserialize_operation_payload
    payload = deserialize_operation_payload(row.operation_payload)
    if payload.get('cluster_id') != cluster.id:
        abort(404)
    data = {'id': row.id, 'status': row.status, 'error': row.error, 'action': payload.get('action')}
    if int(g.user_params['role']) <= 3 and payload.get('action') == 'bootstrap':
        data.update(log=payload.get('installation_log', []), truncated=payload.get('installation_log_truncated', False))
    return jsonify(data=data)


@bp.get('/api/<int:cluster_id>/logs/<int:server_id>')
@api
def logs(cluster_id, server_id):
    operator()
    return jsonify(data=service.logs(current(cluster_id), server_id))
