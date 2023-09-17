import modules.server.server as server_mod


def ping_from_server(server_from: str, server_to: str, action: str) -> str:
    stderr = ''
    action_for_sending = ''
    output1 = ''

    if server_to == '':
        return 'warning: enter a correct IP or DNS name'

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
        return f'error: {stderr}'
    for i in output:
        if i == ' ' or i == '':
            continue
        i = i.strip()
        if 'PING' in i:
            output1 += '<span style="color: var(--link-dark-blue); display: block; margin-top: -5px;">'
        elif 'no reply' in i or 'no answer yet' in i or 'Too many hops' in i or '100% packet loss' in i:
            output1 += '<span style="color: var(--red-color);">'
        elif 'ms' in i and '100% packet loss' not in i:
            output1 += '<span style="color: var(--green-color);">'
        else:
            output1 += '<span>'

        output1 += i + '</span><br />'

    return output1


def telnet_from_server(server_from: str, server_to: str, port_to: str) -> str:
    count_string = 0
    stderr = ''
    output1 = ''

    if server_to == '':
        return 'warning: enter a correct IP or DNS name'

    if server_from == 'localhost':
        action_for_sending = f'echo "exit"|nc {server_to} {port_to} -t -w 1s'
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [f'echo "exit"|nc {server_to} {port_to} -t -w 1s']
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        return f'error: <b>{stderr[5:]}</b>'

    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        if i == 'Ncat: Connection timed out.':
            return f'error: <b>{i[5:]}</b>'
        output1 += i + '<br>'
        count_string += 1
        if count_string > 1:
            break
    return output1

def nslookup_from_server(server_from: str, dns_name: str, record_type: str) -> str:
    count_string = 0
    stderr = ''
    output1 = ''

    if dns_name == '':
        return 'warning: enter a correct DNS name'

    action_for_sending = f'dig {dns_name} {record_type} |grep -e "SERVER\|{dns_name}"'

    if server_from == 'localhost':
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        return 'error: ' + stderr[5:-1]

    output1 += f'<b style="display: block; margin-top:10px;">The <i style="color: var(--blue-color)">{dns_name}</i> domain has the following records:</b>'
    for i in output:
        if 'dig: command not found.' in i:
            return 'error: Install bind-utils before using NSLookup'
        if ';' in i and ';; SERVER:' not in i:
            continue
        if 'SOA' in i and record_type != 'SOA':
            return '<b style="color: red">There are not any records for this type'
        if ';; SERVER:' in i:
            i = i[10:]
            output1 += '<br><b>From NS server:</b><br>'
        i = i.strip()
        output1 += '<i>' + i + '</i><br>'
        count_string += 1

    return output1
