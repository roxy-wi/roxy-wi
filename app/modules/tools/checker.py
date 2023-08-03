from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.roxywi.common as roxywi_common
import modules.roxywi.roxy as roxywi_mod


def load_checker(page: str) -> None:
    groups = sql.select_groups()
    services = roxywi_mod.get_services_status()
    lang = roxywi_common.get_user_lang()
    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/load_telegram.html')
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

    if user_subscription['user_status']:
        haproxy_settings = sql.select_checker_settings(1)
        nginx_settings = sql.select_checker_settings(2)
        keepalived_settings = sql.select_checker_settings(3)
        apache_settings = sql.select_checker_settings(4)
        if page == 'servers.py':
            user_group = roxywi_common.get_user_group(id=1)
            telegrams = sql.get_user_telegram_by_group(user_group)
            slacks = sql.get_user_slack_by_group(user_group)
            pds = sql.get_user_pd_by_group(user_group)
            haproxy_servers = roxywi_common.get_dick_permit(haproxy=1, only_group=1)
            nginx_servers = roxywi_common.get_dick_permit(nginx=1, only_group=1)
            apache_servers = roxywi_common.get_dick_permit(apache=1, only_group=1)
            keepalived_servers = roxywi_common.get_dick_permit(keepalived=1, only_group=1)
        else:
            telegrams = sql.select_telegram()
            slacks = sql.select_slack()
            pds = sql.select_pd()
            haproxy_servers = roxywi_common.get_dick_permit(haproxy=1)
            nginx_servers = roxywi_common.get_dick_permit(nginx=1)
            apache_servers = roxywi_common.get_dick_permit(apache=1)
            keepalived_servers = roxywi_common.get_dick_permit(keepalived=1)

    template = template.render(services=services, telegrams=telegrams, pds=pds, groups=groups, slacks=slacks,
                               user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'],
                               haproxy_servers=haproxy_servers, nginx_servers=nginx_servers, apache_servers=apache_servers,
                               keepalived_servers=keepalived_servers, haproxy_settings=haproxy_settings, nginx_settings=nginx_settings,
                               keepalived_settings=keepalived_settings, apache_settings=apache_settings, page=page, lang=lang)
    print(template)
