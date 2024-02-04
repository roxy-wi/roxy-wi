import json

from flask import render_template, g, request, jsonify
from flask_login import login_required

from app.routes.ha import bp
from middleware import get_user_params, check_services
import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.service.keepalived as keepalived
import modules.service.ha_cluster as ha_cluster


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/<service>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@check_services
@get_user_params()
def cluster_function(service):
    group_id = g.user_params['group_id']
    if request.method == 'GET':
        kwargs = {
            'clusters': sql.select_clusters(group_id),
            'is_needed_tool': common.is_tool('ansible'),
            'user_subscription': roxywi_common.return_user_subscription()
        }

        return render_template('ha_cluster.html', **kwargs)
    elif request.method == 'PUT':
        cluster = json.loads(request.form.get('jsonData'))

        try:
            return ha_cluster.update_cluster(cluster, group_id)
        except Exception as e:
            return f'{e}'
    elif request.method == 'POST':
        cluster = json.loads(request.form.get('jsonData'))

        try:
            return ha_cluster.create_cluster(cluster, group_id)
        except Exception as e:
            return f'{e}'
    elif request.method == 'DELETE':
        cluster_id = int(request.form.get('cluster_id'))
        try:
            return ha_cluster.delete_cluster(cluster_id)
        except Exception as e:
            return f'{e}'


@bp.route('/<service>/get/<int:cluster_id>')
@check_services
@get_user_params()
def get_ha_cluster(service, cluster_id):
    router_id = sql.get_router_id(cluster_id, default_router=1)
    kwargs = {
        'servers': roxywi_common.get_dick_permit(virt=1),
        'clusters': sql.select_cluster(cluster_id),
        'slaves': sql.select_cluster_slaves(cluster_id, router_id),
        'virts': sql.select_clusters_virts(),
        'vips': sql.select_cluster_vips(cluster_id),
        'cluster_services': sql.select_cluster_services(cluster_id),
        'services': sql.select_services(),
        'group_id': g.user_params['group_id'],
        'router_id': router_id,
        'lang': g.user_params['lang']
    }

    return render_template('ajax/ha/clusters.html', **kwargs)


@bp.route('/<service>/settings/<int:cluster_id>')
@check_services
@get_user_params()
def get_cluster_settings(service, cluster_id):
    settings = {}
    clusters = sql.select_cluster(cluster_id)
    router_id = sql.get_router_id(cluster_id, default_router=1)
    slaves = sql.select_cluster_slaves(cluster_id, router_id)
    cluster_services = sql.select_cluster_services(cluster_id)
    vip = sql.select_clusters_vip(cluster_id, router_id)
    return_master = sql.select_clusters_vip_return_master(cluster_id, router_id)
    vip_id = sql.select_clusters_vip_id(cluster_id, router_id)
    is_virt = sql.check_ha_virt(vip_id)
    for cluster in clusters:
        settings.setdefault('name', cluster.name)
        settings.setdefault('desc', cluster.desc)
        settings.setdefault('return_to_master', return_master)
        settings.setdefault('syn_flood', cluster.syn_flood)
        settings.setdefault('vip', vip)
        settings.setdefault('virt_server', is_virt)

    for slave in slaves:
        if slave[31]:
            settings.setdefault('eth', slave[32])

    for c_s in cluster_services:
        if int(c_s.service_id) == 1:
            settings.setdefault('haproxy', 1)
        elif int(c_s.service_id) == 2:
            settings.setdefault('nginx', 1)
        elif int(c_s.service_id) == 4:
            settings.setdefault('apache', 1)

    return jsonify(settings)


@bp.route('/<service>/<int:cluster_id>')
@check_services
@get_user_params()
def show_ha_cluster(service, cluster_id):
    services = []
    service = 'keepalived'
    service_desc = sql.select_service(service)
    router_id = sql.get_router_id(cluster_id, default_router=1)
    servers = sql.select_cluster_master_slaves(cluster_id, g.user_params['group_id'], router_id)
    waf_server = ''
    cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
    keep_alive, stderr = server_mod.subprocess_execute(cmd)
    servers_with_status1 = []
    restart_settings = sql.select_restart_services_settings(service_desc.slug)
    for s in servers:
        servers_with_status = list()
        servers_with_status.append(s[0])
        servers_with_status.append(s[1])
        servers_with_status.append(s[2])
        servers_with_status.append(s[11])
        status1, status2 = keepalived.get_status(s[2])
        servers_with_status.append(status1)
        servers_with_status.append(status2)
        servers_with_status.append(s[22])
        servers_with_status.append(sql.is_master(s[2]))
        servers_with_status.append(sql.select_servers(server=s[2]))

        is_keepalived = sql.select_keepalived(s[2])

        if is_keepalived:
            try:
                cmd = ['sudo kill -USR1 `cat /var/run/keepalived.pid` && sudo grep State /tmp/keepalived.data -m 1 |'
                       'awk -F"=" \'{print $2}\'|tr -d \'[:space:]\' && sudo rm -f /tmp/keepalived.data']
                out = server_mod.ssh_command(s[2], cmd)
                out1 = ('1', out)
                servers_with_status.append(out1)
            except Exception as e:
                servers_with_status.append(str(e))
        else:
            servers_with_status.append('')

        servers_with_status1.append(servers_with_status)

    user_subscription = roxywi_common.return_user_subscription()
    kwargs = {
        'servers': servers_with_status1,
        'waf_server': waf_server,
        'service': service,
        'services': services,
        'service_desc': service_desc,
        'keep_alive': ''.join(keep_alive),
        'restart_settings': restart_settings,
        'user_subscription': user_subscription,
        'clusters': sql.select_ha_cluster_name_and_slaves(),
        'master_slave': sql.is_master(0, master_slave=1),
        'lang': g.user_params['lang']
    }

    return render_template('service.html', **kwargs)


@bp.route('/<service>/slaves/<int:cluster_id>', methods=['GET', 'POST'])
@check_services
@get_user_params()
def get_slaves(service, cluster_id):
    lang = g.user_params['lang']
    if request.method == 'GET':
        router_id = sql.get_router_id(cluster_id, default_router=1)
    else:
        router_id = int(request.form.get('router_id'))
    slaves = sql.select_cluster_slaves(cluster_id, router_id)

    return render_template('ajax/ha/add_vip_slaves.html', lang=lang, slaves=slaves)


@bp.route('/<service>/slaves/servers/<int:cluster_id>')
@check_services
@get_user_params()
def get_server_slaves(service, cluster_id):
    group_id = g.user_params['group_id']
    lang = g.user_params['lang']
    try:
        router_id = sql.get_router_id(cluster_id, default_router=1)
        slaves = sql.select_cluster_slaves(cluster_id, router_id)
    except Exception:
        slaves = ''
    free_servers = sql.select_ha_cluster_not_masters_not_slaves(group_id)

    return render_template('ajax/ha/slave_servers.html', free_servers=free_servers, slaves=slaves, lang=lang)


@bp.route('/<service>/masters')
@check_services
@get_user_params()
def get_masters(service):
    group_id = g.user_params['group_id']
    free_servers = sql.select_ha_cluster_not_masters_not_slaves(group_id)

    return render_template('ajax/ha/masters.html', free_servers=free_servers)


@bp.route('/<service>/settings/<int:cluster_id>/vip/<int:router_id>')
@check_services
def get_vip_settings(service, cluster_id, router_id):
    settings = {}
    return_master = sql.select_clusters_vip_return_master(cluster_id, router_id)
    vip_id = sql.select_clusters_vip_id(cluster_id, router_id)
    is_virt = sql.check_ha_virt(vip_id)
    settings.setdefault('return_to_master', return_master)
    settings.setdefault('virt_server', is_virt)
    return jsonify(settings)


@bp.route('/<service>/<int:cluster_id>/vip', methods=['POST', 'PUT', 'DELETE'])
@check_services
@get_user_params()
def ha_vip(service, cluster_id):
    user_params = g.user_params
    group_id = user_params['group_id']
    json_data = json.loads(request.form.get('jsonData'))
    if request.method == 'PUT':
        router_id = int(json_data['router_id'])
        try:
            ha_cluster.update_vip(cluster_id, router_id, json_data, group_id)
        except Exception as e:
            return f'{e}'
        return 'ok'
    elif request.method == 'POST':
        try:
            ha_cluster.insert_vip(cluster_id, json_data, group_id)
        except Exception as e:
            return f'{e}'

        return 'ok'
    elif request.method == 'DELETE':
        router_id = int(json_data['router_id'])
        try:
            sql.delete_ha_router(router_id)
            return 'ok'
        except Exception as e:
            return f'error: Cannot delete VIP: {e}'
