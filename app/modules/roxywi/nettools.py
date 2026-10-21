import json
from html import escape

import whois
import netaddr
from flask import Response, stream_with_context

import app.modules.server.ssh as mod_ssh
import app.modules.server.server as server_mod
from app.modules.server.command import build_remote_command, build_remote_pipeline, run_local, stream_local
from app.modules.roxywi.error_handler import safe_error_message


def _text_lines(lines) -> list[str]:
    decoded_lines = []
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode('utf-8', errors='backslashreplace')
        decoded_lines.append(line)
    return decoded_lines


def ping_from_server(server_from: str, server_to: str, action: str) -> Response:
    if server_to == '':
        raise Exception('warning: Wrong IP address or name')

    def paint_output(generated):
        for k in generated:
            try:
                k = k.decode('utf-8')
            except Exception:
                yield ''
            for i in k.split('\n'):
                if i == ' ' or i == '':
                    continue
                safe_line = escape(i)
                if 'PING' in i:
                    yield f'<span style="color: var(--link-dark-blue); display: block; margin-top: -5px;">{safe_line}</span><br />\n'
                elif i in ('no reply', 'no answer yet', 'Too many hops', '100% packet loss'):
                    yield f'<span style="color: var(--red-color);">{safe_line}</span><br />\n'
                elif 'ms' in i and '100% packet loss' not in i:
                    yield f'<span style="color: var(--green-color);">{safe_line}</span><br />\n'
                else:
                    yield f'{safe_line}<br />'

    if action in ('nettools_ping', 'ping'):
        executable = 'ping'
        arguments = ['-c', '4', '-W', '1', '-s', '56', '-O', server_to]
    elif action in ('nettools_trace', 'trace'):
        executable = 'tracepath'
        arguments = ['-m', '10', server_to]
    else:
        raise ValueError('Unsupported network action')

    if server_from == 'localhost':
        output = stream_local([executable, *arguments])
        return Response(stream_with_context(paint_output(output)), mimetype='text/html')
    else:
        ssh_generator = mod_ssh.ssh_connect(server_from)
        command = build_remote_command(executable, arguments)
        return Response(stream_with_context(paint_output(ssh_generator.generate(command))), mimetype='text/html')


def telnet_from_server(server_from: str, server_to: str, port_to: int) -> str:
    count_string = 0
    stderr = ''
    output1 = ''

    if server_to == '':
        return 'warning: enter a correct IP or DNS name'
    if port_to is None:
        return 'warning: enter a correct port'

    arguments = [server_to, port_to, '-t', '-w', '1s']
    if server_from == 'localhost':
        result = run_local(['nc', *arguments], input_text='exit\n', timeout=5)
        output = result.stdout_lines
        stderr = result.stderr
    else:
        action_for_sending = build_remote_pipeline([
            ('printf', ['%s', 'exit']),
            ('nc', arguments),
        ])
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)
        output = _text_lines(output)

    if stderr != '':
        return f'error: <b>{escape(stderr[5:])}</b>'

    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        if i == 'Ncat: Connection timed out.':
            return f'error: <b>{escape(i[5:])}</b>'
        output1 += escape(i) + '<br>'
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
    if not record_type:
        return 'warning: choose a DNS record type'

    arguments = [dns_name, record_type]

    if server_from == 'localhost':
        result = run_local(['dig', *arguments], timeout=10)
        output = result.stdout_lines
        stderr = result.stderr
    else:
        command = build_remote_command('dig', arguments)
        output = server_mod.ssh_command(server_from, command, raw=1)
        output = _text_lines(output)

    output = [line for line in output if 'SERVER' in line or dns_name in line]

    if stderr != '':
        return 'error: ' + stderr[5:-1]

    safe_dns_name = escape(dns_name)
    output1 += f'<b style="display: block; margin-top:10px;">The <i style="color: var(--blue-color)">{safe_dns_name}</i> domain has the following records:</b>'
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
        output1 += '<i>' + escape(i) + '</i><br>'
        count_string += 1

    return output1


def whois_check(domain_name: str) -> str:
    if domain_name == '':
        raise Exception('warning: Wrong DNS name')
    try:
        whois_data = json.loads(str(whois.whois(domain_name)))
    except Exception as e:
        return f'error: Cannot get whois from {domain_name}: {safe_error_message(e)}'

    output = (f'<b>Domain name:</b> {escape(str(whois_data["domain_name"]))}<br />'
              f'<b>Registrar:</b> {escape(str(whois_data["registrar"]))} <br />'
              f'<b>Creation date:</b> {escape(str(whois_data["creation_date"]))} <br />'
              f'<b>Expiration date:</b> {escape(str(whois_data["expiration_date"]))} <br />'
              f'<b>Name servers:</b> {escape(str(whois_data["name_servers"]))} <br />'
              f'<b>Status:</b> {escape(str(whois_data["status"]))} <br />')

    if 'emails' in whois_data:
        output += f'<b>Emails:</b> {escape(str(whois_data["emails"]))} <br />'
    if 'org' in whois_data:
        output += f'<b>Organization:</b> {escape(str(whois_data["org"]))} <br />'

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
