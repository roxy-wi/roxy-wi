"""Bind active/runtime and passive/disk certificate targets to one CIB snapshot."""
from pathlib import PurePosixPath
from app.modules.pacemaker import service
from app.modules.pacemaker.xml import configuration
from app.scripts import certificate_cluster_remote as checks
from app.modules.service import common as service_common
from app.modules.roxywi.exception import RoxywiValidationError


def matching(config,settings,server_id):
    result=[]
    for primitive in config.findall('./resources//primitive'):
        try:declared=checks.declaration(primitive,config)
        except ValueError:continue
        kind=declared['class'];name=declared['type'].removesuffix('.service');params=declared['parameters']
        if settings.get('docker'):
            runtime=settings.get('container_runtime',dict(engine='docker',owner='root',unit=''))
            if kind=='systemd' and runtime.get('owner','root')=='root' and runtime.get('unit') and name==runtime['unit'].removesuffix('.service'):
                result.append(declared)
            elif kind=='ocf' and name==runtime.get('engine','docker') and (params.get('name') or declared['id'])==settings['container']:
                result.append(declared)
        elif kind=='systemd' and name==settings['service_unit'].removesuffix('.service'):
            result.append(declared)
        elif kind=='ocf' and name=='haproxy' and str(PurePosixPath(params.get('conffile','/etc/haproxy/haproxy.cfg')))==settings['config_path']:
            result.append(declared)
    if len(result)!=1:raise RoxywiValidationError('Map exactly one static Pacemaker proxy resource to this service/container before staging certificates')
    return result[0]


def plan(cluster,settings):
    remote,xml=service.connection(cluster);config=configuration(xml)
    state=checks.parse(remote.run(['crm_mon','--one-shot','--output-as=xml'],allowed=(0,1,2)))
    result={}
    try:
        for member,server in service.members(cluster):
            data=settings[server.server_id]
            data.setdefault('service_unit',service_common.get_correct_service_name('haproxy',server.server_id))
            declared=matching(config,data,server.server_id)
            mode=checks.role(state,declared['id'],member.name)
            result[server.server_id]=dict(cluster=cluster.name,node=member.name,cib=checks.configuration_digest(xml),declaration=declared,mode=mode)
    except ValueError:
        raise RoxywiValidationError('Cluster members and proxy resources must be online, clean, managed and quorate before certificate staging') from None
    if not any(value['mode']=='active' for value in result.values()):raise RoxywiValidationError('No active proxy certificate target is available')
    return result
