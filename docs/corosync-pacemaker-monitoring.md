# Cluster exporter and daemon Auto Start

## Prometheus exporter

Open **Installation → Monitoring → Corosync / Pacemaker Exporter**. Select a
registered cluster member, the offered release, the listen IP and TCP port, then
select **Install**. The default IP is the member's management address and the
default port is 9664. Install on every member for monitoring during failover.
Only operators with cluster service access can install or inspect this exporter.

The installer uses ClusterLabs **HA Cluster Exporter 1.4.3**, which exports both
Pacemaker and Corosync metrics. The fixed architecture-specific release checksum
is checked before installation. Installation uses the normal Operations queue and
bundled Ansible role, with job-local public SSH host-key pins from the authenticated
Roxy-WI connection. It does not modify the cluster configuration or firewall.
An existing unmanaged exporter binary is refused rather than replaced.

Select **Check metrics and show Prometheus target** to read the running version,
service state, scrape result, metric families and sample count. The same result
contains the endpoint and ready-to-copy Prometheus scrape configuration. Merely
showing this configuration does not register a remote Prometheus server. The
monitoring server must already be allowed to reach the chosen listener.

Examples include `ha_cluster_corosync_quorate`, Corosync member/quorum votes,
Pacemaker node/resource state, failures, maintenance mode and fencing state.
Exporter metrics complement Roxy-WI's internal cluster health/notification checks.
Optional upstream collectors such as SBD/DRBD need the corresponding deployment;
installing this exporter does not install those services.

The service runs read-only cluster queries through discovered native tool paths.
Its systemd unit uses `Restart=on-failure` and filesystem protections. The binary
and a non-secret managed listener record are stored at
`/usr/local/bin/ha_cluster_exporter` and
`/etc/roxy-wi/ha-cluster-exporter.json`. The bundled role supports the fixed
amd64, arm64, ppc64le and s390x artifacts; actual lab qualification used amd64
Debian 13 and Rocky 9.8. Repeated installation of the same release is supported.

## Auto Start for cluster daemons

Open **Services → Corosync / Pacemaker → Monitoring → Auto Start for cluster
daemons**. **Read effective policy** shows Corosync, Pacemaker and, when installed,
qdevice units on every node, their current state, effective restart policy/delay
and whether the override belongs to Roxy-WI.

Choose **Package defaults**, **Auto Start on failure**, or **No automatic restart**,
then **Apply restart policy** and type the cluster name. The queued operation
checks every node and restores prior per-node settings if a write fails. It only
changes managed systemd drop-ins and reloads unit definitions; applying a policy
does not restart or enable any service.

`on-failure` uses a 10-second delay and a limit of three starts per 300 seconds.
A process crash can restart the daemon; an intentional `systemctl stop` remains
stopped. This policy works even while Roxy-WI is unavailable. Returning to package
defaults removes only Roxy-WI's own file:
`/etc/systemd/system/<unit>.service.d/90-roxywi-autostart.conf`. Unmanaged files
at that path are refused; other administrator drop-ins remain intact.

Pacemaker continues to own applications. Roxy-WI discovers cluster-owned HAProxy,
NGINX, Apache and Keepalived resources, reports conflicting legacy proxy Auto Start
flags and disables those flags during the confirmed policy change. Generic proxy
start/stop and re-enabling its independent Auto Start are refused for these owned
applications; use Pacemaker resource controls instead.

This integration uses the host's systemd policies. It does not modify the separate
subscription-distributed proxy `keep_alive` daemon or pretend that it has acquired
a Pacemaker polling adapter.
