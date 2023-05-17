from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod
import modules.provisioning.common as prov_common

form = common.form


def init_server() -> None:
    roxywi_common.check_user_group()
    cmd = 'cd scripts/terraform/ && sudo terraform init -upgrade -no-color'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        if "Terraform initialized in an empty directory" in output[0]:
            print('error: There is not need module')
        elif "mkdir .terraform: permission denied" in output[0]:
            print('error: Cannot init. Check permission to folder')

        print(output[0])


def edit_server() -> None:
    roxywi_common.check_user_group()
    server_id = form.getvalue('editServerId')
    user_group = form.getvalue('editGroup')
    provider_name = form.getvalue('editProviderName')
    params = sql.select_provisioning_params()
    providers = sql.select_providers(int(user_group))
    lang = roxywi_common.get_user_lang()
    show_editing_server = {
        'aws': sql.select_aws_server,
        'do': sql.select_do_server,
        'gcore': sql.select_gcore_server,
    }
    server = show_editing_server[provider_name](server_id=server_id)
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template(f'ajax/provisioning/{provider_name}_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params, lang=lang)
    print(template)


def create_server() -> None:
    roxywi_common.check_user_group()
    workspace = form.getvalue('provisioning_workspace')
    group = form.getvalue('provisioning_group')
    provider_id = form.getvalue('provisioning_provider_id')
    action = form.getvalue('provisioning_action')
    cloud = form.getvalue('provisioning_cloud')
    state_name = ''

    if cloud == 'aws':
        state_name = 'aws_instance'
    elif cloud == 'do':
        state_name = 'digitalocean_droplet'
    elif cloud == 'gcore':
        state_name = 'gcore_instance'

    tfvars = f'{workspace}_{group}_{cloud}.tfvars'
    cmd = f'cd scripts/terraform/ && sudo terraform apply -auto-approve -no-color -input=false -target=module.{cloud}_module -var-file vars/{tfvars}'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        prov_common.show_error(stderr, group, workspace, provider)
    else:
        if cloud == 'aws':
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.aws_module.aws_eip.floating_ip[0]|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'
            output, stderr = server_mod.subprocess_execute(cmd)
            if stderr != '':
                cmd = 'cd scripts/terraform/ && sudo terraform state show module.' + cloud + '_module.' + state_name + '.hapwi|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'
        else:
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.' + cloud + '_module.' + state_name + '.hapwi|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'

        output, stderr = server_mod.subprocess_execute(cmd)
        ips = ''
        for ip in output:
            ips += ip
            ips += ' '

        if cloud == 'gcore':
            ips = ips.split(' ')[0]

        print(ips)
        try:
            sql.update_provisioning_server_status('Created', group, workspace, provider_id, update_ip=ips)
        except Exception as e:
            print(e)

        if cloud == 'gcore':
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.gcore_module.gcore_instance.hapwi|grep "name"|grep -v -e "_name\|name_" |head -1 |awk -F"\\\"" \'{print $2}\''
            output, stderr = server_mod.subprocess_execute(cmd)
            print(':' + output[0])
            try:
                sql.update_provisioning_server_gcore_name(workspace, output[0], group, provider_id)
            except Exception as e:
                print(e)

        roxywi_common.logging('Roxy-WI server', f'Server {workspace} has been {action}', provisioning=1)


def destroy_server() -> None:
    roxywi_common.check_user_group()
    server_id = form.getvalue('provisiningdestroyserver')
    workspace = form.getvalue('servername')
    group = form.getvalue('group')
    cloud_type = form.getvalue('type')
    provider_id = form.getvalue('provider_id')
    tf_workspace = f'{workspace}_{group}_{cloud_type}'
    cmd = f'cd scripts/terraform/ && sudo terraform init -upgrade -no-color && sudo terraform workspace select {tf_workspace}'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        prov_common.show_error(stderr, group, workspace, provider_id)
    else:
        cmd = f'cd scripts/terraform/ && sudo terraform destroy -auto-approve -no-color -target=module.{cloud_type}_module -var-file vars/{tf_workspace}.tfvars'
        output, stderr = server_mod.subprocess_execute(cmd)

        if stderr != '':
            print(f'error: {stderr}')
        else:
            cmd = f'cd scripts/terraform/ && sudo terraform workspace select default && sudo terraform workspace delete -force {tf_workspace}'
            output, stderr = server_mod.subprocess_execute(cmd)

            print('ok')
            roxywi_common.logging('Roxy-WI server', 'Server has been destroyed', provisioning=1)
            try:
                sql.delete_provisioned_servers(server_id)
            except Exception as e:
                print(e)
