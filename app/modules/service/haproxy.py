import os
import requests

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.config.config as config_mod
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config = roxy_wi_tools.GetConfigVar()
form = common.form


def stat_page_action(serv: str) -> None:
    haproxy_user = sql.get_setting('stats_user')
    haproxy_pass = sql.get_setting('stats_password')
    stats_port = sql.get_setting('stats_port')
    stats_page = sql.get_setting('stats_page')

    postdata = {
        'action': form.getvalue('action'),
        's': form.getvalue('s'),
        'b': form.getvalue('b')
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1; rv:20.0) Gecko/20100101 Firefox/20.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate'
    }

    requests.post(f'http://{serv}:{stats_port}/{stats_page}', headers=headers, data=postdata, auth=(haproxy_user, haproxy_pass))


def show_map(serv: str) -> None:
    import networkx as nx
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    stats_port = sql.get_setting('stats_port')
    hap_configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    date = get_date.return_date('config')
    cfg = f'{hap_configs_dir}{serv}-{date}.cfg'

    print(f'<center><h4 style="margin-bottom: 0;">Map from {serv}</h4>')

    error = config_mod.get_config(serv, cfg)
    if error:
        print(error)
    try:
        conf = open(cfg, "r")
    except IOError:
        print('error: Cannot read import config file')
        return

    G = nx.DiGraph()
    node = ""
    line_new2 = [1, ""]
    sections = {'listens': dict(), 'backends': dict()}

    for line in conf:
        if line.startswith('listen') or line.startswith('frontend'):
            if "stats" not in line:
                node = line
        if line.find("backend") == 0:
            node = line
            node = node.split('\n')[0]
            sections['backends'][node] = {'servers': dict()}

        if "bind" in line or (line.startswith('listen') and ":" in line) or (
                line.startswith('frontend') and ":" in line):
            try:
                if "@" not in line:
                    bind = line.split(":")
                else:
                    bind = line.split("@")
                if str(stats_port) not in bind[1]:
                    bind[1] = bind[1].strip(' ')
                    bind = bind[1].split("crt")
                    node = node.strip(' \t\n\r')
                    node = node + ":" + bind[0]
                    node = node.split('\n')[0]
                    sections['listens'][node] = {'servers': dict()}
            except Exception:
                pass

        if "server " in line or "use_backend" in line or "default_backend" in line and "stats" not in line and "#" not in line:
            if "timeout" not in line and "default-server" not in line and "#" not in line and "stats" not in line:
                if "check" in line:
                    line_new = line.split("check")
                else:
                    line_new = line.split("if ")
                if "server" in line:
                    line_new1 = line_new[0].split("server")
                    line_new[0] = line_new1[1]
                    line_new2 = line_new[0].split(":")
                    line_new[0] = line_new2[0]

                line_new[0] = line_new[0].strip(' \t\n\r')

                try:
                    backend_server_port = line_new2[1].strip(' \t\n\r')
                    backend_server_port = 'port: ' + backend_server_port
                except Exception:
                    backend_server_port = ''

                try:
                    sections['listens'][node]['servers'][line_new[0]] = {line_new[0]: backend_server_port}
                except Exception:
                    pass

                try:
                    sections['backends'][node]['servers'][line_new[0]] = {line_new[0]: backend_server_port}
                except Exception:
                    pass
    conf.close()
    os.remove(cfg)

    i, k, j = 0, 0, 0
    backend_servers_len_dict = 1
    backends_from_frontends = []
    backends_servers = []

    for key, val in sections.items():
        if key == 'listens':
            for k2, v2 in val.items():
                i -= 750
                G.add_node(k2, pos=(k, i), label_pos=(k, i + 250))

                for k3, v3 in v2.items():
                    for k4, v4 in v3.items():
                        """ Add backend servers of listens or backend from frontends """
                        i -= 300
                        j += 1
                        server_name = k4

                        if 'default_backend' in k4 or 'use_backend' in k4:
                            backend_name = k4.split(' ')[1]
                            backend_name = 'backend ' + backend_name
                            k4 = backend_name
                            backends_from_frontends.append(k4)

                        if k4 not in backends_servers:
                            if j % 2 == 0:
                                G.add_node(k4, pos=(k + 250, i - 100), label_pos=(k + 250, i - 420))
                            else:
                                G.add_node(k4, pos=(k - 250, i - 370), label_pos=(k - 245, i - 650))

                        if v4[server_name] != '':
                            G.add_edge(k2, k4, port=v4[server_name])
                        else:
                            G.add_edge(k2, k4, port='')

                    for k4, v4 in v3.items():
                        """ Add servers from backends  """
                        i -= 300
                        j -= 1

                        if 'default_backend' in k4 or 'use_backend' in k4:
                            backend_name = k4.split(' ')[1]
                            backend_name = 'backend ' + backend_name
                            k4 = backend_name
                            backends_from_frontends.append(k4)

                            if j % 2 == 0:
                                if len(v3) % 2 == 0:
                                    i += (700 * backend_servers_len_dict) + 700
                                for k5, v5 in sections['backends'][k4]['servers'].items():
                                    i -= 700
                                    s = k + 400
                                    G.add_node(k5, pos=(s + 250, i - 335), label_pos=(s + 215, i - 580))

                                    if v5[k5] != '':
                                        G.add_edge(k4, k5, port=v5[k5])
                                    else:
                                        G.add_edge(k4, k5, port='')

                                    backends_servers.append(k5)
                            else:
                                for k5, v5 in sections['backends'][k4]['servers'].items():
                                    i -= 700
                                    s = k - 400
                                    G.add_node(k5, pos=(s - 250, i - 0), label_pos=(s - 245, i - 270))

                                    if v5[k5] != '':
                                        G.add_edge(k4, k5, port=v5[k5])
                                    else:
                                        G.add_edge(k4, k5, port='')

                                    backends_servers.append(k5)
                                backend_servers_len_dict = len(sections['backends'][k4]['servers'])

                        backends_servers.append(k4)

        elif key == 'backends':
            for k2, v2 in val.items():

                if k2 not in backends_from_frontends:
                    i -= 750
                    G.add_node(k2, pos=(k, i), label_pos=(k, i + 250))

                for k3, v3 in v2.items():
                    for k4, v4 in v3.items():

                        if k4 not in backends_servers:
                            i -= 300
                            j += 1

                            if j % 2 == 0:
                                s = k + 400
                                G.add_node(k4, pos=(s + 250, i - 335), label_pos=(s + 215, i - 580))
                            else:
                                s = k - 400
                                G.add_node(k4, pos=(s - 250, i - 0), label_pos=(s - 245, i - 270))

                        if v4[k4] != '':
                            G.add_edge(k2, k4, port=v4[k4])
                        else:
                            G.add_edge(k2, k4, port='')

                        backends_servers.append(k4)

    pos = nx.get_node_attributes(G, 'pos')
    pos_label = nx.get_node_attributes(G, 'label_pos')
    edge_labels = nx.get_edge_attributes(G, 'port')

    try:
        plt.figure(10, figsize=(10, 20))
        nx.draw(G, pos, with_labels=False, font_weight='bold', width=3, alpha=0.1, linewidths=5)
        nx.draw_networkx_nodes(G, pos, node_color="#5d9ceb", node_size=100, alpha=0.8, node_shape="h")
        nx.draw_networkx_labels(G, pos=pos_label, alpha=1, font_color="#5CB85C", font_size=10)
        nx.draw_networkx_edges(G, pos, width=0.3, alpha=0.7, edge_color="#5D9CEB", arrows=False)
        nx.draw_networkx_edge_labels(G, pos, alpha=0.4, label_pos=0.5, font_color="#5d9ceb", edge_labels=edge_labels,
                                     font_size=8)

        plt.savefig("map.png")
        plt.show()
    except Exception as e:
        print(str(e))

    os.system(
        f"rm -f {os.path.dirname(os.getcwd())}/map*.png && mv map.png {os.path.dirname(os.getcwd())}/map{date}.png")
    print(f'<img src="/map{date}.png" alt="map"></center>')


def runtime_command(serv: str) -> None:
    server_state_file = sql.get_setting('server_state_file')
    haproxy_sock = sql.get_setting('haproxy_sock')
    enable = common.checkAjaxInput(form.getvalue('servaction'))
    backend = common.checkAjaxInput(form.getvalue('servbackend'))

    cmd = f'echo "{enable} {backend}" |sudo socat stdio {haproxy_sock}'

    if form.getvalue('save') == "on":
        save_command = f'echo "show servers state" | sudo socat {haproxy_sock} stdio > {server_state_file}'
        command = [cmd + ';' + save_command]
    else:
        command = [cmd]

    if enable != "show":
        roxywi_common.logging(serv, f'Has been {enable}ed {backend}', login=1, keep_history=1, service='haproxy')
        print(
            f'<center><h3>You {enable} {backend} on HAProxy {serv}. <a href="statsview.py?serv={serv}" '
            f'title="View stat" target="_blank">Look it</a> or <a href="runtimeapi.py" '
            f'title="Runtime API">Edit something else</a></h3><br />')

    print(server_mod.ssh_command(serv, command, show_log="1"))
    action = f'runtimeapi.py {enable} {backend}'
    roxywi_common.logging(serv, action)
