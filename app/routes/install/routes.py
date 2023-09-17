import os
import sys

from flask import render_template, request, redirect, url_for
from flask_login import login_required

from app.routes.install import bp

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod
import modules.service.common as service_common
import modules.service.installation as service_mod
import modules.service.exporter_installation as exp_installation


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('')
def install_monitoring():
    roxywi_auth.page_for_admin(level=2)

    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    is_needed_tool = common.is_tool('ansible')
    geoip_country_codes = sql.select_geoip_country_codes()

    return render_template(
        'install.html', h2=1, role=user_params['role'], user=user, servers=user_params['servers'],
        user_services=user_params['user_services'], lang=user_params['lang'], geoip_country_codes=geoip_country_codes,
        is_needed_tool=is_needed_tool, token=user_params['token']
    )


@bp.route('/ha')
def ha():
    roxywi_auth.page_for_admin(level=2)

    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    is_needed_tool = common.is_tool('ansible')
    user_subscription = roxywi_common.return_user_subscription()
    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=3)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

    return render_template(
        'ha.html', h2=1, role=user_params['role'], user=user, selects=user_params['servers'],
        user_services=user_params['user_services'], user_status=user_subscription['user_status'], lang=user_params['lang'],
        user_plan=user_subscription['user_plan'], is_needed_tool=is_needed_tool, token=user_params['token']
    )


@bp.post('/keepalived', defaults={'slave_kp': None})
@bp.post('/keepalived/<slave_kp>')
def install_keepalived(slave_kp):
    master = request.form.get('master')
    slave = request.form.get('slave')
    eth = request.form.get('interface')
    eth_slave = request.form.get('slave_interface')
    vrrp_ip = request.form.get('vrrpip')
    syn_flood = request.form.get('syn_flood')
    return_to_master = request.form.get('return_to_master')
    haproxy = request.form.get('hap')
    nginx = request.form.get('nginx')
    router_id = request.form.get('router_id')
    virt_server = request.form.get('virt_server')

    try:
        virt_server = int(virt_server)
    except Exception:
        pass

    if not slave_kp:
        try:
            return service_mod.keepalived_master_install(
                master, eth, eth_slave, vrrp_ip, virt_server, syn_flood, return_to_master, haproxy, nginx, router_id
            )
        except Exception as e:
            return f'{e}'
    else:
        try:
            return service_mod.keepalived_slave_install(
                master, slave, eth, eth_slave, vrrp_ip, syn_flood, haproxy, nginx, router_id
            )
        except Exception as e:
            return f'{e}'


@bp.post('/keepalived/add', defaults={'slave_kp': None})
@bp.post('/keepalived/add/<slave_kp>')
def add_extra_vrrp(slave_kp):
    master = request.form.get('master')
    slave = request.form.get('slave')
    eth = request.form.get('interface')
    slave_eth = request.form.get('slave_interface')
    vrrp_ip = request.form.get('vrrpip')
    router_id = request.form.get('router_id')
    return_to_master = request.form.get('return_to_master')
    kp = request.form.get('kp')

    if not slave_kp:
        try:
            return service_mod.keepalived_masteradd(master, eth, slave_eth, vrrp_ip, router_id, return_to_master, kp)
        except Exception as e:
            return f'{e}'
    else:
        try:
            return service_mod.keepalived_slaveadd(slave, eth, slave_eth, vrrp_ip, router_id, kp)
        except Exception as e:
            return f'{e}'


@bp.post('/<service>/<server_ip>')
def install_service(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    docker = common.checkAjaxInput(request.form.get('docker'))
    syn_flood = request.form.get('syn_flood')
    hapver = request.form.get('hapver')

    if service in ('nginx', 'apache'):
        try:
            return service_mod.install_service(server_ip, service, docker, syn_flood)
        except Exception as e:
            return str(e)
    elif service == 'haproxy':
        try:
            return service_mod.install_haproxy(server_ip, syn_flood=syn_flood, hapver=hapver, docker=docker)
        except Exception as e:
            return str(e)
    else:
        return 'warning: Wrong service'


@bp.post('/<service>/master-slave')
def master_slave(service):
    master = request.form.get('master')
    slave = request.form.get('slave')
    server = request.form.get('server')
    docker = request.form.get('docker')

    if service == 'haproxy':
        if server == 'master':
            try:
                return service_mod.install_haproxy(master, server=server, docker=docker, m_or_s='master', master=master, slave=slave)
            except Exception as e:
                return f'{e}'
        elif server == 'slave':
            try:
                return service_mod.install_haproxy(slave, server=server, docker=docker, m_or_s='slave', master=master, slave=slave)
            except Exception as e:
                return f'{e}'
    elif service == 'nginx':
        syn_flood_protect = '1' if request.form.get('syn_flood') == "1" else ''
        if server == 'master':
            try:
                return service_mod.install_service(master, 'nginx', docker, syn_flood_protect, server=server)
            except Exception as e:
                return f'{e}'
        elif server == 'slave':
            try:
                return service_mod.install_service(slave, 'nginx', docker, syn_flood_protect, server=server)
            except Exception as e:
                return f'{e}'


@bp.route('/<service>/version/<server_ip>')
def get_service_version(service, server_ip):
    if service in ('haproxy', 'nginx', 'apache'):
        return service_common.show_service_version(server_ip, service)
    elif service == 'keepalived':
        cmd = ["sudo /usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}'"]
        return server_mod.ssh_command(server_ip, cmd)
    else:
        return 'error: Wrong service'


@bp.post('/exporter/<exporter>')
def install_exporter(exporter):
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))
    ver = common.checkAjaxInput(request.form.get('exporter_v'))
    ext_prom = common.checkAjaxInput(request.form.get('ext_prom'))

    if exporter == 'haproxy':
        return exp_installation.haproxy_exp_installation(server_ip, ver, ext_prom)
    elif exporter in ('nginx', 'apache'):
        return exp_installation.nginx_apache_exp_installation(server_ip, exporter, ver, ext_prom)
    elif exporter in ('keepalived', 'node'):
        return exp_installation.node_keepalived_exp_installation(exporter, server_ip, ver, ext_prom)
    else:
        return 'error: Wrong exporter'


@bp.route('/exporter/<exporter>/version/<server_ip>')
def get_exporter_version(exporter, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    return service_common.get_exp_version(server_ip, exporter)


@bp.route('/grafana')
def install_grafana():
    try:
        return service_mod.grafana_install()
    except Exception as e:
        return f'{e}'


@bp.route('/waf/<service>/<server_ip>')
def install_waf(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service == 'haproxy':
        try:
            return service_mod.waf_install(server_ip)
        except Exception as e:
            return str(e)
    elif service == 'nginx':
        try:
            return service_mod.waf_nginx_install(server_ip)
        except Exception as e:
            return str(e)
    else:
        return 'error: Wrong service'


@bp.post('/geoip')
def install_geoip():
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))
    geoip_update = common.checkAjaxInput(request.form.get('update'))
    service = request.form.get('service')

    try:
        return service_mod.geoip_installation(server_ip, geoip_update, service)
    except Exception as e:
        return str(e)


@bp.route('/geoip/<service>/<server_ip>')
def check_geoip(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
    cmd = [f"ls {service_dir}geoip/"]
    return server_mod.ssh_command(server_ip, cmd)
