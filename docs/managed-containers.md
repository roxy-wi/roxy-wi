# Managed components with Docker and Podman

This guide covers proxies and the standalone quorum witness managed **from the
Roxy-WI GUI**. Deploying the Roxy-WI controller itself is a separate feature and
guide. All remote operations use the registered server's existing SSH credentials;
the controller does not need a Docker or Podman socket.

The recorded VM checks below cover Debian 13.7 and Rocky Linux 9.8 with SELinux
enforcing. Other supported package profiles still require qualification in the
target environment; these results do not qualify arbitrary application images.

## Install a proxy

Open **Installation → Proxy service**, select the registered server and choose
**Runtime: Native / Docker / Podman**. The Keepalived HA wizard offers the same
runtime choice for its HAProxy, NGINX and Apache components.

![Proxy installation runtime selection](screenshots/managed-containers/installation.png)

| Selection | Result |
| --- | --- |
| Native | Existing distribution-package installation |
| Docker | Existing Docker installation, retaining legacy API compatibility |
| Podman | Rootful, host-network Podman container supervised by a native Quadlet |

Podman proxy provisioning requires Python 3.9+ available as `python3`, systemd,
cgroup v2 and **Podman 4.9+ with Quadlet**.
The supported Debian/Ubuntu or EL 8/9 repositories must supply that version;
Roxy-WI does not add repositories or change kernel boot settings. The installer
installs Podman/OpenSSL, selects a fixed proxy image recipe and pins its resolved
image ID. It does not install Docker, Docker Ansible collections or a compatibility
socket. SELinux enforcement remains enabled.

The supported recipes are HAProxy (the selected HAProxy version), NGINX and Apache.
Keepalived's new-install path remains native. Rootless provisioning of new users,
subordinate IDs and login/boot policy is not performed by this installer; existing
rootless proxy containers can be adopted below.

The installer refuses an active native proxy, an unrelated container/systemd unit,
changed deployment paths or existing configuration without a managed receipt.
Use adoption for an existing deployment. It prepares a new configuration privately
before installing it, retains a receipt for interrupted preparation and reports
safe failures in Operations. Re-running a managed installation preserves its
configuration, refreshes the selected image and restores the previous unit on
activation failure. It does not import another deployment's volumes.

System units are `roxywi-haproxy.service`, `roxywi-nginx.service` and
`roxywi-apache.service`, from `/etc/containers/systemd/*.container`. Configuration
and service log directories are persistent bind mounts. HAProxy reuses the host
rsyslog/logrotate recipe; NGINX/Apache write their existing configured log paths.
Optional SYN-flood tuning remains a host setting selected during installation.

## Adopt an existing container

Open the selected service's **Settings** dialog:

1. Choose Docker or Podman and its **Linux container owner** (`root` for rootful).
2. Select **Discover containers** and choose a result. Roxy-WI reads names, images,
   running state, network mode, mounts and matching Quadlets; it does not return
   environment variables or registry credentials.
3. Review the container name and optional lifecycle unit, select **Run in a
   container**, and save. Saving a binding does not recreate or move the container.
4. For HAProxy, use the existing source-discovery panel to verify the real startup
   arguments and configuration files. Custom wrappers are not executed or guessed.

Changing/inspecting another container identity requires a server administrator
(role 1/2). An operator can use an already authorized binding. Group and service
permissions still apply. Discovery and lifecycle commands never fall back to
another engine or another owner if the selected runtime is unavailable.

Without an explicit per-server container name, the service default is always read
from that server's group. The same name is resolved in an HTTP request and in a
background worker, including manual, Let's Encrypt and external-provider certificate
deployment. An unrelated current request group never selects the target's default.

Rootless owners need a working user runtime (`/run/user/UID`, user manager and
container engine). Lifecycle units must be real Podman Quadlets whose `SourcePath`
and `ContainerName` match that container. A unit name such as `sshd.service` cannot
be used as an arbitrary systemd control. Without a verified unit, existing
container lifecycle uses the chosen engine directly; its boot policy remains the
owner's deployment policy.

Configuration, runtime statistics, service actions, NGINX maps and certificate
transport use the saved engine/owner/name. Rootless Runtime API and HTTP-statistics
requests enter a pinned, verified container network namespace over SSH; they do
not assume its private bridge address is reachable from the controller. The target
needs `nsenter` from util-linux and the existing noninteractive sudo permission.
The process identity is checked again before probing. Unverifiable namespaces
(including deployments hiding their container identity from cgroups) are refused.

HAProxy must run in master-worker mode (`-W`/`-Ws`) as container PID 1 for graceful
reload. Roxy-WI verifies this and uses `USR2`. NGINX and Apache use their normal
reload signal. Stop/start actions work with stopped Quadlet containers; restart
restrictions and Pacemaker ownership checks still apply. Keepalived container
adoption requires rootful host networking and Keepalived as PID 1; rootless
Keepalived is rejected.

## Configuration and certificates

Use writable **directory** mounts for configuration; a read-only or single-file
mount cannot follow atomic file replacement. NGINX/Apache and Keepalived now use
the shared validation transaction: a failed validation/reload restores the prior
file, and a test does not leave the candidate active. File identities and Change
Center versions retain the original selected path, including spaces/Unicode.

New Podman proxies mount `/var/lib/roxy-wi/certificates/SERVICE` and store that
service-specific directory in their settings. SSL catalogs/uploads and HAProxy
certificate operations use it. Existing installations retain their configured
certificate directory. Global `/etc/ssl/certs` is not relabeled as a private
container volume. Atomic certificate replacement preserves existing extended
attributes, including SELinux labels; label-copy failure on a SELinux host fails
the operation rather than being accepted as success.

An adopted deployment must expose its configured certificate directory through
its persistent mounts. HAProxy configuration and Runtime API certificate checks
report missing/ambiguous mounts instead of guessing. Pacemaker-owned service
start/stop/restart belongs to the cluster; Auto Start and direct service actions
must not compete with its resource agents.

## Standalone quorum witness

Open **Installation → Corosync / Pacemaker → Install witness only**, select an
independent registered host and choose **Native / Docker / Podman**.

![Standalone witness runtime selection](screenshots/managed-containers/witness.png)

Docker and Podman build the same fixed Debian qnetd image and retain its NSS
database under `/var/lib/roxy-wi/qnetd/data`. Podman uses a managed systemd
supervisor for the stable container name: this permits reviewed image replacement,
rollback and NSS migration while maintaining a single restart owner. The process
runs as UID/GID 65532 with a read-only root, dropped capabilities and private
temporary runtime storage. Podman-specific tmpfs ownership uses its supported
mount syntax; Docker keeps its existing options.

The selected engine is recorded on the witness host and in the durable Operations
request. Status, signing, logs, image updates, native conversion and trust migration
all use that engine. Existing container witness data cannot be rebound to a
different engine by pressing Install. Docker-to-Podman data migration is not an
implicit installation operation.

For an existing native witness, select the destination engine, **Review migration**,
then **Convert to selected engine**. The reviewed digest includes that engine.
The existing backup, independent rollback timer, CA preservation and TLS/vote
checks remain mandatory. Image refresh, conversion back to native and recovery
stay in the existing GUI sections. A witness remains outside cluster members;
running a container on a cluster member does not create an independent vote.

Podman witness provisioning includes the `nftables` userspace tool needed by
minimal installations using Netavark's nft backend, including when Podman was
already installed. This does not enable a firewall service or change host rules.
The image build needs working DNS and outbound package access from its build
network. On a host also running Docker, an existing `FORWARD=DROP` policy can
block a Podman bridge; the administrator must provide the required forwarding.
Roxy-WI does not flush rules or change that policy.

Reviewed migration verifies the native CA's exported identity and trust before
switching. Different NSS builds can interpret copied trust metadata differently;
the destination copy receives only the original reviewed trust for that same CA.
The original native database is retained. An unexpected CA or unsupported native
trust fails preparation. TLS/votes on every attached member must pass before the
independent rollback timer is committed.

## API compatibility and verification

Existing `docker: true/false` fields retain their meaning. New installation
requests can set `services.SERVICE.container_engine` to `native`, `docker` or
`podman`; a top-level `container_engine` supplies the legacy single-service form.
An explicit service engine takes precedence over its old Docker boolean.
Witness installation accepts `container_engine` with the same three values.
Native-to-container migration review/apply accepts `container_engine=docker|podman`.

Run the normal unit/product/browser tests. The real proxy integration check is
`tests/integration/test_podman_proxy_linux.py` with `ROXYWI_TEST_PODMAN_PROXY=1`;
the real witness image/restart check is `tests/integration/test_podman_witness_linux.py`
with `ROXYWI_TEST_PODMAN_WITNESS=1`. Both opt-ins require rootful Podman **inside a
disposable Linux container**, and use isolated container networks. They do not
start native host services. The nested witness build uses only its outer CI
container's network to reach its DNS stub.

Local checks used Ubuntu 24.04 ARM64, Python 3.12 and Podman 4.9.3, real HAProxy
3.0.10/NGINX/Apache images and a freshly built qnetd image. They cover statistics,
namespace access, configuration rejection/rollback/reload and witness CA retention.
## Recorded VM qualification — 29 October 2026

| Profile | Observed result |
| --- | --- |
| Debian 13.7 / Podman 5.4.2 | GUI-installed HAProxy 3.3.1, NGINX 1.30.6 and Apache 2.4.69; actual version/process status and all four lifecycle actions passed. |
| Rocky Linux 9.8 / Podman 5.8.2, SELinux enforcing | The same GUI installation and lifecycle checks passed. |
| Existing rootless HAProxy, both platforms | GUI discovery, binding to the ordinary Linux owner and exact Quadlet, startup-source discovery, Runtime status and reload/restart/stop/start passed; original rootful bindings were restored. |
| Reboot, both spare VMs | Rootful HAProxy/Apache and the adopted rootless HAProxy started automatically after a verified fresh boot. |
| Reboot, Debian/Rocky cluster members | Independently approved maintenance surrounded actual reboots; NGINX and HAProxy autostart and healthy reviewed return were observed on both members. |
| Attached witness, Debian and Rocky | Native → Podman → image refresh → native passed, preserving the CA and verifying TLS plus a nonzero witness vote on every attached member. |

The 32 rootful lifecycle actions covered four NGINX members and two HAProxy/Apache
hosts per service. Tests found and fixed missing NGINX MIME assets under a complete
configuration-directory mount and stopped Quadlet status handling. The witness
test found the minimal-host nft dependency and cross-distribution NSS trust
difference. The rejected first Rocky migration automatically restored native qnetd
and its votes; the corrected full round trip then passed. These are test outcomes,
not successful deployments inferred merely from saved settings.

The opt-in `test_podman_witness_migration_refresh_and_reviewed_return` in
`tests/integration/test_pacemaker_workflows_live.py` reproduces the attached witness
round trip using private HTTP lab configuration with `podman_witnesses` server IDs.
The entire live workflow module requires explicit opt-in and is skipped in normal
CI. These temporary proxy tests do not qualify Pacemaker proxy boot ownership,
every rootless networking configuration or arbitrary OCI workloads.

The Quadlet requirements and mount/ownership syntax follow the official
[Podman 4.9 Quadlet reference](https://docs.podman.io/en/v4.9.3/markdown/podman-systemd.unit.5.html)
and [Podman run reference](https://docs.podman.io/en/v4.9.3/markdown/podman-run.1.html).
