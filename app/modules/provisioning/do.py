import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.provisioning.common as prov_common

form = common.form


def validate() -> None:
    if form.getvalue('dovalidate'):
        workspace = form.getvalue('dovalidate')
        group = form.getvalue('do_create_group')
    else:
        workspace = form.getvalue('doeditvalidate')
        group = form.getvalue('do_edit_group')

    cmd = f'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.do_module -var-file vars/{workspace}_{group}_do.tfvars'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')


def new_workspace() -> None:
    workspace = form.getvalue('doworkspace')
    group = form.getvalue('do_create_group')
    provider = form.getvalue('do_create_provider')
    region = form.getvalue('do_create_regions')
    size = form.getvalue('do_create_size')
    oss = form.getvalue('do_create_oss')
    ssh_name = form.getvalue('do_create_ssh_name')
    ssh_ids = form.getvalue('do_create_ssh_ids')
    backup = form.getvalue('do_create_backup')
    privet_net = form.getvalue('do_create_private_net')
    floating_ip = form.getvalue('do_create_floating_net')
    monitoring = form.getvalue('do_create_monitoring')
    firewall = form.getvalue('do_create_firewall')

    cmd = f'cd scripts/terraform/ && sudo terraform workspace new {workspace}_{group}_do'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        prov_common.show_error(stderr, group, workspace, provider)
    else:
        if sql.add_server_do(
                region, size, privet_net, floating_ip, ssh_ids, ssh_name, workspace, oss, firewall, monitoring,
                backup, provider, group, 'Creating'
        ):
            prov_common.show_new_server(workspace, group, 'do')


def edit_workspace() -> None:
    workspace = form.getvalue('doeditworkspace')
    group = form.getvalue('do_edit_group')
    provider = form.getvalue('do_edit_provider')
    size = form.getvalue('do_edit_size')
    oss = form.getvalue('do_edit_oss')
    ssh_name = form.getvalue('do_edit_ssh_name')
    ssh_ids = form.getvalue('do_edit_ssh_ids')
    backup = form.getvalue('do_edit_backup')
    privet_net = form.getvalue('do_edit_private_net')
    floating_ip = form.getvalue('do_edit_floating_net')
    monitoring = form.getvalue('do_edit_monitoring')
    firewall = form.getvalue('do_edit_firewall')
    server_id = form.getvalue('server_id')
    try:
        if sql.update_server_do(
                size, privet_net, floating_ip, ssh_ids, ssh_name, oss, firewall, monitoring, backup, provider,
                group, 'Creating', server_id
        ):

            cmd = f'cd scripts/terraform/ && sudo terraform workspace select {workspace}_{group}_do'
            output, stderr = server_mod.subprocess_execute(cmd)

            if stderr != '':
                prov_common.show_error(stderr, group, workspace, provider)
            else:
                print('ok')
    except Exception as e:
        print(e)


def create_vars() -> None:
    if form.getvalue('dovars'):
        dovars = form.getvalue('dovars')
        group = form.getvalue('do_create_group')
        provider = form.getvalue('do_create_provider')
        region = form.getvalue('do_create_regions')
        size = form.getvalue('do_create_size')
        oss = form.getvalue('do_create_oss')
        ssh_name = form.getvalue('do_create_ssh_name')
        ssh_ids = form.getvalue('do_create_ssh_ids')
        backup = form.getvalue('do_create_backup')
        privet_net = form.getvalue('do_create_private_net')
        floating_ip = form.getvalue('do_create_floating_net')
        monitoring = form.getvalue('do_create_monitoring')
        firewall = form.getvalue('do_create_firewall')
    else:
        dovars = form.getvalue('doeditvars')
        group = form.getvalue('do_edit_group')
        provider = form.getvalue('do_edit_provider')
        region = form.getvalue('do_edit_regions')
        size = form.getvalue('do_edit_size')
        oss = form.getvalue('do_edit_oss')
        ssh_name = form.getvalue('do_edit_ssh_name')
        ssh_ids = form.getvalue('do_edit_ssh_ids')
        backup = form.getvalue('do_edit_backup')
        privet_net = form.getvalue('do_edit_private_net')
        floating_ip = form.getvalue('do_edit_floating_net')
        monitoring = form.getvalue('do_edit_monitoring')
        firewall = form.getvalue('do_edit_firewall')

    token = sql.select_do_provider(provider)

    cmd = f'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={region} ' \
          f'group={group} size={size} os={oss} floating_ip={floating_ip} ssh_ids={ssh_ids} server_name={dovars} ' \
          f'token={token} backup={backup} monitoring={monitoring} privet_net={privet_net} firewall={firewall} ' \
          f'floating_ip={floating_ip} ssh_name={ssh_name} cloud=do"'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')
