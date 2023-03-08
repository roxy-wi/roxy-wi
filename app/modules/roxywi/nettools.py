import modules.common.common as common
import modules.server.server as server_mod

form = common.form


def ping_from_server() -> None:
    server_from = common.checkAjaxInput(form.getvalue('nettools_icmp_server_from'))
    server_to = common.checkAjaxInput(form.getvalue('nettools_icmp_server_to'))
    server_to = common.is_ip_or_dns(server_to)
    action = common.checkAjaxInput(form.getvalue('nettools_action'))
    stderr = ''
    action_for_sending = ''

    if server_to == '':
        print('warning: enter a correct IP or DNS name')
        return

    if action == 'nettools_ping':
        action_for_sending = 'ping -c 4 -W 1 -s 56 -O '
    elif action == 'nettools_trace':
        action_for_sending = 'tracepath -m 10 '

    action_for_sending = action_for_sending + server_to

    if server_from == 'localhost':
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1, timeout=15)

    if stderr != '':
        print(f'error: {stderr}')
        return
    for i in output:
        if i == ' ' or i == '':
            continue
        i = i.strip()
        if 'PING' in i:
            print('<span style="color: var(--link-dark-blue); display: block; margin-top: -20px;">')
        elif 'no reply' in i or 'no answer yet' in i or 'Too many hops' in i or '100% packet loss' in i:
            print('<span style="color: var(--red-color);">')
        elif 'ms' in i and '100% packet loss' not in i:
            print('<span style="color: var(--green-color);">')
        else:
            print('<span>')

        print(i + '</span><br />')


def telnet_from_server() -> None:
    server_from = common.checkAjaxInput(form.getvalue('nettools_telnet_server_from'))
    server_to = common.checkAjaxInput(form.getvalue('nettools_telnet_server_to'))
    server_to = common.is_ip_or_dns(server_to)
    port_to = common.checkAjaxInput(form.getvalue('nettools_telnet_port_to'))
    count_string = 0
    stderr = ''

    if server_to == '':
        print('warning: enter a correct IP or DNS name')
        return

    if server_from == 'localhost':
        action_for_sending = f'echo "exit"|nc {server_to} {port_to} -t -w 1s'
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [f'echo "exit"|nc {server_to} {port_to} -t -w 1s']
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print(f'error: <b>{stderr[5:]}</b>')
        return

    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        if i == 'Ncat: Connection timed out.':
            print(f'error: <b>{i[5:]}</b>')
            break
        print(i + '<br>')
        count_string += 1
        if count_string > 1:
            break


def nslookup_from_server() -> None:
    server_from = common.checkAjaxInput(form.getvalue('nettools_nslookup_server_from'))
    dns_name = common.checkAjaxInput(form.getvalue('nettools_nslookup_name'))
    dns_name = common.is_ip_or_dns(dns_name)
    record_type = common.checkAjaxInput(form.getvalue('nettools_nslookup_record_type'))
    count_string = 0
    stderr = ''

    if dns_name == '':
        print('warning: enter a correct DNS name')
        return

    action_for_sending = f'dig {dns_name} {record_type} |grep -e "SERVER\|{dns_name}"'

    if server_from == 'localhost':
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print('error: ' + stderr[5:-1])
        return

    print(
        f'<b style="display: block; margin-top:10px;">The <i style="color: var(--blue-color)">{dns_name}</i> domain has the following records:</b>')
    for i in output:
        if 'dig: command not found.' in i:
            print('error: Install bind-utils before using NSLookup')
            break
        if ';' in i and ';; SERVER:' not in i:
            continue
        if 'SOA' in i and record_type != 'SOA':
            print('<b style="color: red">There are not any records for this type')
            break
        if ';; SERVER:' in i:
            i = i[10:]
            print('<br><b>From NS server:</b><br>')
        i = i.strip()
        print('<i>' + i + '</i><br>')
        count_string += 1
