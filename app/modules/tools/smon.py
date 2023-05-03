from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.common as roxywi_common

form = common.form


def create_smon() -> None:
    user_group = roxywi_common.get_user_group(id=1)
    server = common.checkAjaxInput(form.getvalue('newsmon'))
    port = common.checkAjaxInput(form.getvalue('newsmonport'))
    enable = common.checkAjaxInput(form.getvalue('newsmonenable'))
    http = common.checkAjaxInput(form.getvalue('newsmonproto'))
    uri = common.checkAjaxInput(form.getvalue('newsmonuri'))
    body = common.checkAjaxInput(form.getvalue('newsmonbody'))
    group = common.checkAjaxInput(form.getvalue('newsmongroup'))
    desc = common.checkAjaxInput(form.getvalue('newsmondescription'))
    telegram = common.checkAjaxInput(form.getvalue('newsmontelegram'))
    slack = common.checkAjaxInput(form.getvalue('newsmonslack'))
    pd = common.checkAjaxInput(form.getvalue('newsmonpd'))

    try:
        port = int(port)
    except Exception:
        print('SMON error: port must number')
        return None
    if port > 65535 or port < 0:
        print('SMON error: port must be 0-65535')
        return None
    if port == 80 and http == 'https':
        print('SMON error: Cannot be HTTPS with 80 port')
        return None
    if port == 443 and http == 'http':
        print('SMON error: Cannot be HTTP with 443 port')
        return None

    last_id = sql.insert_smon(server, port, enable, http, uri, body, group, desc, telegram, slack, pd, user_group)
    if last_id:
        lang = roxywi_common.get_user_lang()
        smon = sql.select_smon_by_id(last_id)
        pds = sql.get_user_pd_by_group(user_group)
        slacks = sql.get_user_slack_by_group(user_group)
        telegrams = sql.get_user_telegram_by_group(user_group)
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/show_new_smon.html')
        template = template.render(smon=smon, telegrams=telegrams, slacks=slacks, pds=pds, lang=lang)
        print(template)
        roxywi_common.logging('SMON', f' A new server {server} to SMON has been add ', roxywi=1, login=1)


def update_smon() -> None:
    smon_id = common.checkAjaxInput(form.getvalue('id'))
    ip = common.checkAjaxInput(form.getvalue('updateSmonIp'))
    port = common.checkAjaxInput(form.getvalue('updateSmonPort'))
    en = common.checkAjaxInput(form.getvalue('updateSmonEn'))
    http = common.checkAjaxInput(form.getvalue('updateSmonHttp'))
    body = common.checkAjaxInput(form.getvalue('updateSmonBody'))
    telegram = common.checkAjaxInput(form.getvalue('updateSmonTelegram'))
    slack = common.checkAjaxInput(form.getvalue('updateSmonSlack'))
    pd = common.checkAjaxInput(form.getvalue('updateSmonPD'))
    group = common.checkAjaxInput(form.getvalue('updateSmonGroup'))
    desc = common.checkAjaxInput(form.getvalue('updateSmonDesc'))

    try:
        port = int(port)
    except Exception:
        print('SMON error: port must number')
        return None
    if port > 65535 or port < 0:
        print('SMON error: port must be 0-65535')
        return None
    if port == 80 and http == 'https':
        print('SMON error: Cannot be https with 80 port')
        return None
    if port == 443 and http == 'http':
        print('SMON error: Cannot be HTTP with 443 port')
        return None

    roxywi_common.check_user_group()
    try:
        if sql.update_smon(smon_id, ip, port, body, telegram, slack, pd, group, desc, en):
            print("Ok")
            roxywi_common.logging('SMON', f' The SMON server {ip} has been update ', roxywi=1, login=1)
    except Exception as e:
        print(e)


def show_smon() -> None:
    user_group = roxywi_common.get_user_group(id=1)
    lang = roxywi_common.get_user_lang()
    sort = common.checkAjaxInput(form.getvalue('sort'))
    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/smon_dashboard.html')
    template = template.render(smon=sql.smon_list(user_group), sort=sort, lang=lang, update=1)
    print(template)


def delete_smon() -> None:
    user_group = roxywi_common.get_user_group(id=1)
    smon_id = common.checkAjaxInput(form.getvalue('smondel'))

    if roxywi_common.check_user_group():
        try:
            if sql.delete_smon(smon_id, user_group):
                print('Ok')
                roxywi_common.logging('SMON', ' The server from SMON has been delete ', roxywi=1, login=1)
        except Exception as e:
            print(e)
