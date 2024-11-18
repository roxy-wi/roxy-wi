import json

import whois
import netaddr
from flask import Response, stream_with_context

import app.modules.server.ssh as mod_ssh
import app.modules.server.server as server_mod


def ping_from_server(server_from: str, server_to: str, action: str) -> Response:
    action_for_sending = ''
    if server_to == '':
        raise Exception('warning: Wrong IP address or name')

    def paint_output(generated):
        yield '<div class="ping_pre">'
        for k in generated:
            try:
                k = k.decode('utf-8')
            except Exception:
                yield ''
            for i in k.split('\n'):
                if i == ' ' or i == '':
                    continue
                if 'PING' in i:
                    yield f'<span style="color: var(--link-dark-blue); display: block; margin-top: -5px;">{i}</span><br />\n'
                elif i in ('no reply', 'no answer yet', 'Too many hops', '100% packet loss'):
                    yield f'<span style="color: var(--red-color);">{i}</span><br />\n'
                elif 'ms' in i and '100% packet loss' not in i:
                    yield f'<span style="color: var(--green-color);">{i}</span><br />\n'
                else:
                    yield f'{i}<br />'
        yield '</div>'

    if action == 'nettools_ping':
        action_for_sending = 'ping -c 4 -W 1 -s 56 -O '
    elif action == 'nettools_trace':
        action_for_sending = 'tracepath -m 10 '

    action_for_sending = action_for_sending + server_to

    if server_from == 'localhost':
        return Response(stream_with_context(paint_output(server_mod.subprocess_execute_stream(action_for_sending))), mimetype='text/html')
    else:
        ssh_generator = mod_ssh.ssh_connect(server_from)
        return Response(stream_with_context(paint_output(ssh_generator.generate(action_for_sending))), mimetype='text/html')


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
        action_for_sending = f'echo "exit"|nc {server_to} {port_to} -t -w 1s'
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


def whois_check(domain_name: str) -> str:
    if domain_name == '':
        raise Exception('warning: Wrong DNS name')
    try:
        whois_data = json.loads(str(whois.whois(domain_name)))
    except Exception as e:
        return f'error: Cannot get whois from {domain_name}: {e}'

    output = (f'<b>Domain name:</b> {whois_data["domain_name"]}<br />'
              f'<b>Registrar:</b> {whois_data["registrar"]} <br />'
              f'<b>Creation date:</b> {whois_data["creation_date"]} <br />'
              f'<b>Expiration date:</b> {whois_data["expiration_date"]} <br />'
              f'<b>Name servers:</b> {whois_data["name_servers"]} <br />'
              f'<b>Status:</b> {whois_data["status"]} <br />')

    if 'emails' in whois_data:
        output += f'<b>Emails:</b> {whois_data["emails"]} <br />'
    if 'org' in whois_data:
        output += f'<b>Organization:</b> {whois_data["org"]} <br />'

    return output


def ip_calc(ip_add: str, netmask: int) -> dict[str, str]:
    ip = netaddr.IPNetwork(f'{ip_add}/{netmask}')
    ip_output = {
        'address': str(ip.ip),
        'network': str(ip.network),
        'netmask': str(ip.netmask),
        'broadcast': str(ip.broadcast),
        'hosts': str(ip.size),
        'min': str(ip[1]),
        'max': str(ip[-2])
    }
    return ip_output
