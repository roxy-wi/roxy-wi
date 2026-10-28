# Standalone quorum witness in Docker

Use **Installation → Corosync / Pacemaker → Install witness only**, choose an
independent registered host, select **Use Docker** and confirm installation.
Leave the checkbox clear for the native package/systemd variant. The server entry
and its existing SSH credentials refer to the Docker **host**, not a container.
The deployment choice is stored in the durable Operations task.

The controller itself can run in Docker, packages or Helm. It does not need a
Docker socket: Web/Operations manage the selected host over the existing SSH
connection. The witness must remain outside all registered clusters and independent
of their nodes' failure domains. A container on a cluster node is not an independent
witness. Fencing is still required.

## Host prerequisites

The same supported systemd host profiles apply: Debian 11+, Ubuntu 20.04+, EL 8/9,
Python 3.8+ as `python3`, SSH and non-interactive sudo. Use **Check platform** first.
Docker Engine must be running, or its packages must be available from enabled
host repositories. When the Docker CLI is missing, the installer installs
`docker.io` on Debian/Ubuntu, or `docker-ce`, `docker-ce-cli`, `containerd.io` on EL,
and enables Docker. It does not add external Docker repositories, alter an existing
daemon configuration or grant users membership in the Docker group. A broken or
unreachable existing Docker daemon must be repaired before retrying. The Debian
Docker CLI split is handled by adding `docker-cli` when that package is available.

The build requires access to Docker Hub's official `debian:trixie-slim` image and
the image's Debian package repositories. The host's architecture must be available
in that official image and package set. The only live container qualification is
amd64 on Debian 13; other host profiles/architectures need their own qualification.

Allow cluster nodes to reach the host on **TCP 5403**. The container uses host
networking, as existing Roxy-WI Docker service installations do. Installation
refuses an occupied port, active Corosync/Pacemaker, a Proxmox host, an existing
native witness CA/service or an unmanaged container using its reserved name.
It does not change firewall rules or disable SELinux.

## Image, runtime and certificate persistence

Roxy-WI builds its fixed, versioned-in-source Dockerfile locally; no arbitrary
image name, shell fragment or launch flags are accepted through the form/API.
The base image tag and Debian packages resolve at build time, so builds are not
byte-for-byte reproducible across repository updates. The resulting image is tagged
with the recipe hash and launched by its resolved **image ID**. It is reused on
repeated installation, rather than silently pulling or recreating a running witness.

| Setting | Value |
| --- | --- |
| Container | `roxywi-qnetd` |
| Persistent host directory | `/var/lib/roxy-wi/qnetd/data` |
| Mount inside container | `/etc/corosync/qnetd` (read/write, SELinux private relabel) |
| Certificate database | `data/nssdb`, including the witness CA/private key and signed cluster certificates |
| Restart policy | `unless-stopped` |
| Daemon | Foreground qnetd, TLS required and client certificate checking enabled |
| Runtime restrictions | UID/GID 65532, read-only root filesystem, all capabilities dropped, no-new-privileges, bounded processes/memory/CPU, temporary `/run` and `/tmp` |
| Readiness | Actual `corosync-qnetd-tool -s` response and initialized CA; the image also provides a Docker health check |

The package-generated build-time NSS database is removed in the same Docker build
step; no CA is shipped in the image. First start creates a new CA in persistent
storage. Reinstallation/start preserves it. A partial NSS database is an error,
not permission to create a replacement CA. The witness CA private key stays on the
witness. Registration exchanges public CA/certificate requests and signed cluster
certificates over SSH; the qdevice client PKCS#12 bundle is distributed between
cluster nodes over the existing SSH transport.

Back up the complete persistent directory securely, preserving ownership and
permissions. Losing it means losing the witness identity: recreating the container
with a new CA will not restore the cluster nodes' trust. Keep the application DB
and its encryption key in the controller's normal backups too.

## Attach and verify

Installing the standalone witness does **not** change cluster membership or quorum.
After installation:

1. Select the managed cluster in **Services → Corosync / Pacemaker → Quorum / witness**.
2. Load current membership settings and choose the registered Docker host as witness.
3. Create, validate and apply the reviewed Corosync change.
4. Roxy-WI detects its managed container, runs certificate signing inside it and
   configures native qdevice clients on the cluster nodes with TLS required.
5. Check diagnostics on every node for a connected qdevice and an available vote.

Adding further nodes reads the CA through the same native/container-aware witness
protocol. Docker does not require SSH or a second SSH credential inside the
container. Adopted custom transports and migration between existing witness CAs
retain their documented restrictions.

## Failure and recovery

**Read status** reports native/Docker mode, running state, version and CA fingerprint.
Installation/task errors remain visible in Operations. For host-side investigation,
use `docker logs roxywi-qnetd`, `docker inspect roxywi-qnetd` and the host's Docker
journal. If the installation outcome is unknown, inspect the container, port and
persistent data before retrying.

- A repeated successful installation starts/reuses the matching managed container
  and preserves its image/CA.
- A differently labelled container or unexpected bind mount is refused.
- Existing data without the managed container is refused: recover it explicitly;
  installation never discards it or generates a new identity over it.
- A changed image recipe requires an explicit planned image upgrade with the same
  persistent storage. The installer does not automatically replace a working image.
- Switching native/Docker deployment is an explicit migration. Use the separate
  [guided native-to-Docker conversion](corosync-pacemaker-witness-migration.md);
  the installation checkbox does not perform that conversion.

Keep a backup and verify the CA fingerprint and actual qdevice vote after any
recovery, image upgrade or host restart. See the
[verification record](corosync-pacemaker-verification.md) for tested scope.

Protocol/background: [upstream qnetd manual](https://github.com/corosync/corosync-qdevice/blob/main/man/corosync-qnetd.8)
and [certificate helper](https://github.com/corosync/corosync-qdevice/blob/main/qdevices/corosync-qnetd-certutil.sh).
