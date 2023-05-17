import os
import http.cookies

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.common as roxywi_common

form = common.form


def create_provider() -> None:
    roxywi_common.check_user_group()
    is_add = False
    provider_name = common.checkAjaxInput(form.getvalue('new_provider_name'))
    provider_group = common.checkAjaxInput(form.getvalue('new_provider_group'))
    provider_token = common.checkAjaxInput(form.getvalue('new_provider_token'))
    cloud = common.checkAjaxInput(form.getvalue('new_provider_cloud'))

    if cloud == 'do':
        if sql.add_provider_do(provider_name, provider_group, provider_token):
            is_add = True

    elif cloud == 'aws':
        provider_secret = common.checkAjaxInput(form.getvalue('aws_new_secret'))

        if sql.add_provider_aws(provider_name, provider_group, provider_token, provider_secret):
            is_add = True

    elif cloud == 'gcore':
        provider_pass = common.checkAjaxInput(form.getvalue('gcore_new_pass'))

        if sql.add_provider_gcore(provider_name, provider_group, provider_token, provider_pass):
            is_add = True

    if is_add:
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_uuid = cookie.get('uuid')
        group_id = roxywi_common.get_user_group(id=1)
        role_id = sql.get_user_role_by_uuid(user_uuid.value, group_id)
        params = sql.select_provisioning_params()
        providers = sql.select_providers(provider_group, key=provider_token)

        if role_id == 1:
            groups = sql.select_groups()
        else:
            groups = ''

        lang = roxywi_common.get_user_lang()
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/provisioning/providers.html')
        template = template.render(providers=providers, role=role_id, groups=groups, user_group=provider_group,
                                   adding=1, params=params, lang=lang)
        print(template)


def delete_provider() -> None:
    roxywi_common.check_user_group()
    try:
        if sql.delete_provider(common.checkAjaxInput(form.getvalue('providerdel'))):
            print('Ok')
            roxywi_common.logging('Roxy-WI server', 'Provider has been deleted', provisioning=1)
    except Exception as e:
        print(e)


def edit_DO_provider(provider_id: int) -> None:
    roxywi_common.check_user_group()
    new_name = form.getvalue('edit_do_provider_name')
    new_token = form.getvalue('edit_do_provider_token')

    try:
        if sql.update_do_provider(new_name, new_token, provider_id):
            print('ok')
            roxywi_common.logging('Roxy-WI server', f'Provider has been edited. New name is {new_name}', provisioning=1)
    except Exception as e:
        print(e)


def edit_gcore_provider(provider_id: int) -> None:
    roxywi_common.check_user_group()
    new_name = form.getvalue('edit_gcore_provider_name')
    new_user = form.getvalue('edit_gcore_provider_user')
    new_pass = form.getvalue('edit_gcore_provider_pass')

    try:
        if sql.update_gcore_provider(new_name, new_user, new_pass, provider_id):
            print('ok')
            roxywi_common.logging('Roxy-WI server', f'Provider has been edited. New name is {new_name}', provisioning=1)
    except Exception as e:
        print(e)


def edit_aws_provider(provider_id: int) -> None:
    roxywi_common.check_user_group()
    new_name = form.getvalue('edit_aws_provider_name')
    new_key = form.getvalue('edit_aws_provider_key')
    new_secret = form.getvalue('edit_aws_provider_secret')

    try:
        if sql.update_aws_provider(new_name, new_key, new_secret, provider_id):
            print('ok')
            roxywi_common.logging('Roxy-WI server', f'Provider has been edited. New name is {new_name}', provisioning=1)
    except Exception as e:
        print(e)
