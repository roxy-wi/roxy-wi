import app.modules.server.server as server_mod


def get_status(server_ip: str) -> tuple:
    out1 = []
    h = (['', ''],)
    try:
        cmd = [
            "/usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}' && systemctl status keepalived |"
            "grep -e 'Active' |awk '{print $2, $9$10$11$12$13}' && ps ax |grep keepalived|grep -v grep |wc -l"
        ]
        out = server_mod.ssh_command(server_ip, cmd)
        for k in out.split():
            out1.append(k)
        h = (out1,)
        servers_with_status1= h
        servers_with_status2= h
    except Exception:
        servers_with_status1 = h
        servers_with_status2 = h

    return servers_with_status1, servers_with_status2
