from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.common as roxywi_common

form = common.form


def show_error(stderr: str, group: str, workspace: str, provider: str) -> None:
    stderr = stderr.strip()
    stderr = repr(stderr)
    stderr = stderr.replace("'", "")
    stderr = stderr.replace("\'", "")
    sql.update_provisioning_server_status('Error', group, workspace, provider)
    sql.update_provisioning_server_error(stderr, group, workspace, provider)
    print('error: ' + stderr)


def show_new_server(workspace: str, group: str, cloud: str) -> None:
    user_params = roxywi_common.get_users_params()
    new_server = sql.select_provisioned_servers(new=workspace, group=group, type=cloud)
    params = sql.select_provisioning_params()
    lang = roxywi_common.get_user_lang()
    providers = sql.select_providers(group)

    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/provisioned_servers.html')
    template = template.render(servers=new_server, groups=sql.select_groups(), user_group=group, providers=providers,
                               role=user_params['role'], adding=1, params=params, lang=lang)
    print(template)
