from flask import render_template, redirect, url_for

import modules.db.sql as sql
import modules.roxywi.roxy as roxywi_mod
import modules.roxywi.common as roxywi_common


def load_checker() -> None:
    groups = sql.select_groups()
    services = roxywi_mod.get_services_status()
    keepalived_settings = ''
    haproxy_settings = ''
    apache_settings = ''
    nginx_settings = ''
    keepalived_servers = ''
    haproxy_servers = ''
    apache_servers = ''
    nginx_servers = ''
    telegrams = ''
    slacks = ''
    pds = ''

    try:
        user_subscription = roxywi_common.return_user_status()
    except Exception as e:
        user_subscription = roxywi_common.return_unsubscribed_user_status()
        roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if user_subscription['user_status']:
        haproxy_settings = sql.select_checker_settings(1)
        nginx_settings = sql.select_checker_settings(2)
        keepalived_settings = sql.select_checker_settings(3)
        apache_settings = sql.select_checker_settings(4)
        user_group = roxywi_common.get_user_group(id=1)
        telegrams = sql.get_user_telegram_by_group(user_group)
        slacks = sql.get_user_slack_by_group(user_group)
        pds = sql.get_user_pd_by_group(user_group)
        haproxy_servers = roxywi_common.get_dick_permit(haproxy=1, only_group=1)
        nginx_servers = roxywi_common.get_dick_permit(nginx=1, only_group=1)
        apache_servers = roxywi_common.get_dick_permit(apache=1, only_group=1)
        keepalived_servers = roxywi_common.get_dick_permit(keepalived=1, only_group=1)

    return render_template(
        'ajax/load_telegram.html', services=services, telegrams=telegrams, pds=pds, groups=groups, slacks=slacks,
        user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], haproxy_servers=haproxy_servers,
        nginx_servers=nginx_servers, apache_servers=apache_servers, keepalived_servers=keepalived_servers, haproxy_settings=haproxy_settings,
        nginx_settings=nginx_settings, keepalived_settings=keepalived_settings, apache_settings=apache_settings,
        role=user_params['role'], lang=user_params['lang']
    )


def update_haproxy_settings(setting_id, email, service_alert, backend_alert, maxconn_alert, telegram_id, slack_id, pd_id) -> None:
    if sql.update_haproxy_checker_settings(email, telegram_id, slack_id, pd_id, service_alert, backend_alert,
                                           maxconn_alert, setting_id):
        print('ok')
    else:
        print('error: Cannot update Checker settings')


def update_keepalived_settings(setting_id, email, service_alert, backend_alert, telegram_id, slack_id, pd_id) -> None:
    if sql.update_keepalived_checker_settings(email, telegram_id, slack_id, pd_id, service_alert, backend_alert,
                                              setting_id):
        print('ok')
    else:
        print('error: Cannot update Checker settings')


def update_service_settings(setting_id, email, service_alert, telegram_id, slack_id, pd_id) -> None:
    if sql.update_service_checker_settings(email, telegram_id, slack_id, pd_id, service_alert, setting_id):
        print('ok')
    else:
        print('error: Cannot update Checker settings')
