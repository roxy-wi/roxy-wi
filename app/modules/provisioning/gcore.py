import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.provisioning.common as prov_common

form = common.form


def create_vars() -> None:
    if form.getvalue('gcorevars'):
        gcorevars = form.getvalue('gcorevars')
        group = form.getvalue('gcore_create_group')
        provider = form.getvalue('gcore_create_provider')
        region = form.getvalue('gcore_create_regions')
        project = form.getvalue('gcore_create_project')
        size = form.getvalue('gcore_create_size')
        oss = form.getvalue('gcore_create_oss')
        ssh_name = form.getvalue('gcore_create_ssh_name')
        volume_size = form.getvalue('gcore_create_volume_size')
        volume_type = form.getvalue('gcore_create_volume_type')
        delete_on_termination = form.getvalue('gcore_create_delete_on_termination')
        network_name = form.getvalue('gcore_create_network_name')
        firewall = form.getvalue('gcore_create_firewall')
        network_type = form.getvalue('gcore_create_network_type')
    elif form.getvalue('gcoreeditvars'):
        gcorevars = form.getvalue('gcoreeditvars')
        group = form.getvalue('gcore_edit_group')
        provider = form.getvalue('gcore_edit_provider')
        region = form.getvalue('gcore_edit_regions')
        project = form.getvalue('gcore_edit_project')
        size = form.getvalue('gcore_edit_size')
        oss = form.getvalue('gcore_edit_oss')
        ssh_name = form.getvalue('gcore_edit_ssh_name')
        volume_size = form.getvalue('gcore_edit_volume_size')
        volume_type = form.getvalue('gcore_edit_volume_type')
        delete_on_termination = form.getvalue('gcore_edit_delete_on_termination')
        network_name = form.getvalue('gcore_edit_network_name')
        firewall = form.getvalue('gcore_edit_firewall')
        network_type = form.getvalue('gcore_edit_network_type')

    try:
        gcore_user, gcore_pass = sql.select_gcore_provider(provider)
    except Exception as e:
        print(e)

    cmd = 'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={} ' \
          'group={} size={} os={} network_name={} volume_size={} server_name={} username={} ' \
          'pass={} firewall={} network_type={} ssh_name={} delete_on_termination={} project={} volume_type={} ' \
          'cloud=gcore"'.format(region, group, size, oss, network_name, volume_size, gcorevars, gcore_user, gcore_pass,
                                firewall, network_type, ssh_name, delete_on_termination, project, volume_type)

    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')


def validate() -> None:
    if form.getvalue('gcorevalidate'):
        workspace = form.getvalue('gcorevalidate')
        group = form.getvalue('gcore_create_group')
    else:
        workspace = form.getvalue('gcoreeditvalidate')
        group = form.getvalue('gcore_edit_group')

    cmd = f'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.gcore_module -var-file vars/{workspace}_{group}_gcore.tfvars'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')


def new_workspace() -> None:
    workspace = form.getvalue('gcoreworkspace')
    group = form.getvalue('gcore_create_group')
    provider = form.getvalue('gcore_create_provider')
    region = form.getvalue('gcore_create_regions')
    project = form.getvalue('gcore_create_project')
    size = form.getvalue('gcore_create_size')
    oss = form.getvalue('gcore_create_oss')
    ssh_name = form.getvalue('gcore_create_ssh_name')
    volume_size = form.getvalue('gcore_create_volume_size')
    volume_type = form.getvalue('gcore_create_volume_type')
    delete_on_termination = form.getvalue('gcore_create_delete_on_termination')
    network_type = form.getvalue('gcore_create_network_type')
    firewall = form.getvalue('gcore_create_firewall')
    network_name = form.getvalue('gcore_create_network_name')

    cmd = f'cd scripts/terraform/ && sudo terraform workspace new {workspace}_{group}_gcore'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        prov_common.show_error(stderr, group, workspace, provider)
    else:
        try:
            if sql.add_server_gcore(
                    project, region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
                    provider, group, 'Creating', delete_on_termination, volume_type
            ):
                prov_common.show_new_server(workspace, group, 'gcore')
        except Exception as e:
            print(e)


def edit_workspace() -> None:
    workspace = form.getvalue('gcoreeditworkspace')
    group = form.getvalue('gcore_edit_group')
    provider = form.getvalue('gcore_edit_provider')
    region = form.getvalue('gcore_edit_regions')
    project = form.getvalue('gcore_edit_project')
    size = form.getvalue('gcore_edit_size')
    oss = form.getvalue('gcore_edit_oss')
    ssh_name = form.getvalue('gcore_edit_ssh_name')
    volume_size = form.getvalue('gcore_edit_volume_size')
    volume_type = form.getvalue('gcore_edit_volume_type')
    delete_on_termination = form.getvalue('gcore_edit_delete_on_termination')
    network_type = form.getvalue('gcore_edit_network_type')
    firewall = form.getvalue('gcore_edit_firewall')
    network_name = form.getvalue('gcore_edit_network_name')
    server_id = form.getvalue('server_id')

    try:
        if sql.update_server_gcore(
                region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
                provider, group, 'Editing', server_id, delete_on_termination, volume_type, project
        ):

            try:
                cmd = f'cd scripts/terraform/ && sudo terraform workspace select {workspace}_{group}_gcore'
                output, stderr = server_mod.subprocess_execute(cmd)
            except Exception as e:
                print('error: ' + str(e))

            if stderr != '':
                prov_common.show_error(stderr, group, workspace, provider)
            else:
                print('ok')
    except Exception as e:
        print(e)
