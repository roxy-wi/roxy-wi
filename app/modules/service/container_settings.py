"""Map existing Docker settings and explicit OCI bindings to the runtime connector."""
from app.modules.connectors import containers
from app.modules.db import service as service_sql, sql
from app.modules.db.db_model import Server


def runtime(server_id, service):
    # Missing settings retain the existing rootful Docker behavior.
    def setting(key, default):
        value = service_sql.select_service_setting(server_id, service, 'container_' + key)
        return default if value in (None, '', '0') else value
    return containers.validate(dict(engine=setting('engine', 'docker'), owner=setting('owner', 'root'), unit=setting('unit', '')))


def name(server_id, service):
    value = service_sql.select_service_setting(server_id, service, 'container_name')
    if value in (None, '', '0'):
        value = sql.get_setting(service + '_container_name', group_id=Server.get_by_id(server_id).group_id)
    return containers.name(value)


def context(server_id, service):
    spec = runtime(server_id, service)
    return {'container_runtime': spec} if spec != containers.validate() else {}


def certificate_directory(server, service):
    value = service_sql.select_service_setting(server.server_id, service, 'certificate_directory')
    if value not in (None, '', '0'):
        if value != '/var/lib/roxy-wi/certificates/' + service:
            raise ValueError('Invalid managed certificate directory')
        return value
    return sql.get_setting('cert_path', group_id=server.group_id)


def command(server_id, service, arguments=None, *, action=None):
    spec = runtime(server_id, service)
    if action == 'reload' and service == 'haproxy':
        action = 'haproxy-reload'
    return containers.shell(spec, arguments, container=name(server_id, service), action=action)


def discover(server, spec):
    import json
    from app.modules.pacemaker.remote import Remote
    script=containers.embedded() + ('import json,sys\n'
        'try:\n print(json.dumps(module.inspect_host(json.loads(sys.argv[1]))))\n'
        'except Exception:\n print(json.dumps({"error":"Cannot inspect this engine and owner; check installation, user runtime and permissions"}));sys.exit(0)\n')
    result=json.loads(Remote(server).run(['python3','-c',script,json.dumps(containers.validate(spec))],timeout=180))
    if result.get('error'):
        raise ValueError(result['error'])
    return result


def service_status(server,service):
    import json
    from app.modules.pacemaker.remote import Remote
    script=containers.embedded()+('import json,sys\n'
        'data=json.loads(sys.argv[1])\n'
        'print(json.dumps(module.service_status(data["runtime"],data["name"],data["service"])))\n')
    data=dict(runtime=runtime(server.server_id,service),name=name(server.server_id,service),service=service)
    return json.loads(Remote(server).run(['python3','-c',script,json.dumps(data)],timeout=60))


def is_running(server, service):
    import json
    from app.modules.pacemaker.remote import Remote
    script = containers.embedded() + ('import json,sys\ndata=json.loads(sys.argv[1])\n'
        'print(json.dumps(bool(module.container_state(data["runtime"],data["name"])["State"]["Running"])))\n')
    data = dict(runtime=runtime(server.server_id, service), name=name(server.server_id, service))
    return json.loads(Remote(server).run(['python3', '-c', script, json.dumps(data)], timeout=90))


def keepalived_state(server):
    import json
    from app.modules.pacemaker.remote import Remote
    script=containers.embedded()+'import json,sys\ndata=json.loads(sys.argv[1])\nprint(module.keepalived_state(data["runtime"],data["name"]))\n'
    data=dict(runtime=runtime(server.server_id,'keepalived'),name=name(server.server_id,'keepalived'))
    return Remote(server).run(['python3','-c',script,json.dumps(data)],timeout=45).strip()
