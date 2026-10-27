"""Read only host facts used by the cluster registration form."""
import json
from app.modules.pacemaker.adoption import server_for
from app.modules.pacemaker.remote import Remote

SOURCE = r'''
import ipaddress, json, pathlib, socket, subprocess
result = subprocess.run(['ip', '-j', 'address', 'show'], capture_output=True, text=True, timeout=15, check=True)
addresses = []
for interface in json.loads(result.stdout):
    for address in interface.get('addr_info', []):
        value = address.get('local', '')
        try: parsed = ipaddress.ip_address(value)
        except ValueError: continue
        if parsed.is_loopback or parsed.is_link_local or address.get('scope') != 'global': continue
        addresses.append({'address': value, 'prefix': address.get('prefixlen'), 'interface': interface['ifname']})
active = [unit for unit in ('corosync', 'pacemaker', 'corosync-qnetd')
          if subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0]
print(json.dumps({'hostname': socket.gethostname().split('.')[0], 'fqdn': socket.getfqdn(),
                  'addresses': addresses[:128], 'active_cluster_services': active,
                  'existing_witness_data': pathlib.Path('/var/lib/roxy-wi/qnetd/data').exists()}))
'''


def read(server_id, group_id):
    return json.loads(Remote(server_for(server_id, group_id)).run(['python3', '-c', SOURCE]))
