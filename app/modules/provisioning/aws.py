import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.provisioning.common as prov_common

form = common.form


def validate() -> None:
    if form.getvalue('awsvalidate'):
        workspace = form.getvalue('awsvalidate')
        group = form.getvalue('aws_create_group')
    else:
        workspace = form.getvalue('awseditvalidate')
        group = form.getvalue('aws_edit_group')

    cmd = f'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.aws_module -var-file vars/{workspace}_{group}_aws.tfvars'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
    else:
        print('ok')


def new_workspace() -> None:
    workspace = form.getvalue('awsworkspace')
    group = form.getvalue('aws_create_group')
    provider = form.getvalue('aws_create_provider')
    region = form.getvalue('aws_create_regions')
    size = form.getvalue('aws_create_size')
    oss = form.getvalue('aws_create_oss')
    ssh_name = form.getvalue('aws_create_ssh_name')
    volume_size = form.getvalue('aws_create_volume_size')
    volume_type = form.getvalue('aws_create_volume_type')
    delete_on_termination = form.getvalue('aws_create_delete_on_termination')
    floating_ip = form.getvalue('aws_create_floating_net')
    firewall = form.getvalue('aws_create_firewall')
    public_ip = form.getvalue('aws_create_public_ip')

    cmd = f'cd scripts/terraform/ && sudo terraform workspace new {workspace}_{group}_aws'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        prov_common.show_error(stderr, group, workspace, provider)
    else:
        try:
            if sql.add_server_aws(
                    region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall,
                    provider, group, 'Creating', delete_on_termination, volume_type
            ):
                prov_common.show_new_server(workspace, group, 'aws')
        except Exception as e:
            print(e)


def edit_workspace() -> None:
    workspace = form.getvalue('awseditworkspace')
    group = form.getvalue('aws_editing_group')
    provider = form.getvalue('aws_editing_provider')
    region = form.getvalue('aws_editing_regions')
    size = form.getvalue('aws_editing_size')
    oss = form.getvalue('aws_editing_oss')
    ssh_name = form.getvalue('aws_editing_ssh_name')
    volume_size = form.getvalue('aws_editing_volume_size')
    volume_type = form.getvalue('aws_editing_volume_type')
    delete_on_termination = form.getvalue('aws_editing_delete_on_termination')
    floating_ip = form.getvalue('aws_editing_floating_net')
    firewall = form.getvalue('aws_editing_firewall')
    public_ip = form.getvalue('aws_editing_public_ip')
    server_id = form.getvalue('server_id')

    try:
        if sql.update_server_aws(
                region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall,
                provider, group, 'Editing', server_id, delete_on_termination, volume_type
        ):

            try:
                cmd = f'cd scripts/terraform/ && sudo terraform workspace select {workspace}_{group}_aws'
                output, stderr = server_mod.subprocess_execute(cmd)
            except Exception as e:
                print(f'error: {e}')

            if stderr != '':
                prov_common.show_error(stderr, group, workspace, provider)
            else:
                print('ok')
    except Exception as e:
        print(e)


def create_vars() -> None:
    if form.getvalue('awsvars'):
        awsvars = common.checkAjaxInput(form.getvalue('awsvars'))
        group = common.checkAjaxInput(form.getvalue('aws_create_group'))
        provider = common.checkAjaxInput(form.getvalue('aws_create_provider'))
        region = common.checkAjaxInput(form.getvalue('aws_create_regions'))
        size = common.checkAjaxInput(form.getvalue('aws_create_size'))
        oss = common.checkAjaxInput(form.getvalue('aws_create_oss'))
        ssh_name = common.checkAjaxInput(form.getvalue('aws_create_ssh_name'))
        volume_size = common.checkAjaxInput(form.getvalue('aws_create_volume_size'))
        volume_type = common.checkAjaxInput(form.getvalue('aws_create_volume_type'))
        delete_on_termination = common.checkAjaxInput(form.getvalue('aws_create_delete_on_termination'))
        floating_ip = common.checkAjaxInput(form.getvalue('aws_create_floating_net'))
        firewall = common.checkAjaxInput(form.getvalue('aws_create_firewall'))
        public_ip = common.checkAjaxInput(form.getvalue('aws_create_public_ip'))
    else:
        awsvars = common.checkAjaxInput(form.getvalue('awseditvars'))
        group = common.checkAjaxInput(form.getvalue('aws_editing_group'))
        provider = common.checkAjaxInput(form.getvalue('aws_editing_provider'))
        region = common.checkAjaxInput(form.getvalue('aws_editing_regions'))
        size = common.checkAjaxInput(form.getvalue('aws_editing_size'))
        oss = common.checkAjaxInput(form.getvalue('aws_editing_oss'))
        ssh_name = common.checkAjaxInput(form.getvalue('aws_editing_ssh_name'))
        volume_size = common.checkAjaxInput(form.getvalue('aws_editing_volume_size'))
        volume_type = common.checkAjaxInput(form.getvalue('aws_editing_volume_type'))
        delete_on_termination = common.checkAjaxInput(form.getvalue('aws_editing_delete_on_termination'))
        floating_ip = common.checkAjaxInput(form.getvalue('aws_editing_floating_net'))
        firewall = common.checkAjaxInput(form.getvalue('aws_editing_firewall'))
        public_ip = common.checkAjaxInput(form.getvalue('aws_editing_public_ip'))

    aws_key, aws_secret = sql.select_aws_provider(provider)

    cmd = f'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={region} ' \
          f'group={group} size={size} os={oss} floating_ip={floating_ip} volume_size={volume_size} server_name={awsvars} ' \
          f'AWS_ACCESS_KEY={aws_key} AWS_SECRET_KEY={aws_secret} firewall={firewall} public_ip={public_ip} ' \
          f'ssh_name={ssh_name} delete_on_termination={delete_on_termination} volume_type={volume_type} cloud=aws"'

    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')
