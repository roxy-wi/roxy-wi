from flask import render_template, redirect, url_for

import app.modules.db.group as group_sql
import app.modules.db.channel as channel_sql
import app.modules.db.checker as checker_sql
import app.modules.tools.common as tools_common
import app.modules.roxywi.common as roxywi_common


def load_checker() -> str:
    try:
        user_subscription = roxywi_common.return_user_status()
    except Exception as e:
        user_subscription = roxywi_common.return_unsubscribed_user_status()
        roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

    try:
        user_params = roxywi_common.get_users_params()
    except Exception:
        return redirect(url_for('login_page'))

    kwargs = {
        'user_subscription': user_subscription,
        'user_params': user_params,
        'lang': user_params['lang']
    }

    if user_subscription['user_status']:
        user_group = roxywi_common.get_user_group(id=1)
        kwargs.setdefault('services', tools_common.get_services_status())
        kwargs.setdefault('telegrams', channel_sql.get_user_telegram_by_group(user_group))
        kwargs.setdefault('pds', channel_sql.get_user_pd_by_group(user_group))
        kwargs.setdefault('mms', channel_sql.get_user_mm_by_group(user_group))
        kwargs.setdefault('groups', group_sql.select_groups())
        kwargs.setdefault('slacks', channel_sql.get_user_slack_by_group(user_group))
        kwargs.setdefault('haproxy_servers', roxywi_common.get_dick_permit(haproxy=1, only_group=1))
        kwargs.setdefault('nginx_servers', roxywi_common.get_dick_permit(nginx=1, only_group=1))
        kwargs.setdefault('apache_servers', roxywi_common.get_dick_permit(apache=1, only_group=1))
        kwargs.setdefault('keepalived_servers', roxywi_common.get_dick_permit(keepalived=1, only_group=1))
        kwargs.setdefault('user_subscription', user_subscription)
        kwargs.setdefault('user_params', user_params)
        kwargs.setdefault('lang', user_params['lang'])
        kwargs.setdefault('haproxy_settings', checker_sql.select_checker_settings(1))
        kwargs.setdefault('nginx_settings', checker_sql.select_checker_settings(2))
        kwargs.setdefault('keepalived_settings', checker_sql.select_checker_settings(3))
        kwargs.setdefault('apache_settings', checker_sql.select_checker_settings(4))

    return render_template('ajax/load_checker.html', **kwargs)


def update_haproxy_settings(setting_id, email, service_alert, backend_alert, maxconn_alert, telegram_id, slack_id, pd_id, mm_id) -> str:
    if checker_sql.update_haproxy_checker_settings(email, telegram_id, slack_id, pd_id, mm_id, service_alert, backend_alert,
                                           maxconn_alert, setting_id):
        return 'ok'
    else:
        return 'error: Cannot update Checker settings'


def update_keepalived_settings(setting_id, email, service_alert, backend_alert, telegram_id, slack_id, pd_id, mm_id) -> str:
    if checker_sql.update_keepalived_checker_settings(email, telegram_id, slack_id, pd_id, mm_id, service_alert, backend_alert,
                                              setting_id):
        return 'ok'
    else:
        return 'error: Cannot update Checker settings'


def update_service_settings(setting_id, email, service_alert, telegram_id, slack_id, pd_id, mm_id) -> str:
    if checker_sql.update_service_checker_settings(email, telegram_id, slack_id, pd_id, mm_id, service_alert, setting_id):
        return 'ok'
    else:
        return 'error: Cannot update Checker settings'
