# Guided witness conversion, image update and trust migration

Open **Installation → Corosync / Pacemaker → Install witness only**, select the
registered native witness and expand **Convert an existing native witness to
Docker**. This workflow keeps the same host/IP, TCP 5403, CA and existing cluster
certificates. It does not change Corosync configuration or rotate client trust.

1. Select **Review migration**. Roxy-WI reads the native database identity and
   connected cluster names. Every connected cluster must be registered in the
   active group; its members must be online, quorate and using this witness over
   active TLS with a vote. Review the displayed CA fingerprint and cluster list.
2. Select **Convert to Docker**, type the witness server name and confirm.
   The reviewed source digest, host identity and cluster membership are checked
   again in the durable Operations worker. Concurrent cluster operations are
   excluded while conversion runs.
3. Preparation installs missing Docker packages from enabled host repositories,
   builds/reuses the fixed image and takes a private host-side backup. An isolated
   container checks a copy of the original NSS certificate and private-key database
   before the native service is stopped. Debian's split `docker-cli` package is
   included when available. An incompatible database stops the conversion.
4. A host-side systemd timer is armed for **180 seconds**. Roxy-WI stops native
   qnetd and starts the restricted managed container using a copy of the existing
   database. Only filesystem ownership of the copied data changes; no CA or cluster
   certificates are generated. The original native database remains in place.
5. Roxy-WI waits for TLS votes on every attached node. Only after this succeeds is
   the native unit disabled, conversion committed and the recovery timer cancelled.
   The page reports Docker mode and the same CA fingerprint.

The witness connection briefly drops/reconnects during the switch. All cluster
members must therefore be healthy beforehand; converting a witness during an
existing node outage is refused. Fencing remains configured and enabled.

## Recovery through the web

If switching or node verification fails, the worker restores the original native
service. If the controller/network fails after switchover, the independent timer
runs the same recovery on the witness host. The original native enablement state
is restored, and the unsuccessful Docker data is retained privately rather than
discarded. A timer that runs late cannot undo a committed conversion.

Select **Review migration** again to read an unfinished journal. The page enables
**Recover native witness**, which requires the server name and queues the recovery
through Operations. Recovery rechecks server/actor permissions and verifies the
restored votes. **Read witness logs** displays bounded native/Docker logs in the
same GUI. No SSH session or copying of a CA private key between hosts is required
for this supported conversion/recovery workflow.

Source backups, copied data and recovery state remain under
`/var/lib/roxy-wi/qnetd/migrations/<id>` with a private parent directory. The saved
host recovery program runs as root; its state is written atomically. CA private
keys never enter the web response, application operation payload or image build.
The committed mode receipt lets later qdevice setup/reinstallation reuse the
container while retaining the original native database for backup purposes.

## Boundaries

The guided conversion currently supports a **standard native qnetd → Docker on the
same host**, with the distribution's default listener and no custom qnetd flags.
It refuses unknown connected clusters, custom listener/daemon arguments,
unreachable/unhealthy members, changed database identities, unmanaged containers,
orphaned target data and Proxmox hosts. The existing Docker prerequisites and
qualification limits in the [Docker witness guide](corosync-pacemaker-witness-docker.md)
apply. It does not silently add external repositories or change host firewall rules.

Separate reviewed workflows below implement reverse conversion, image refresh,
CA rotation and witness-host migration. Recovery applies to an unfinished operation;
a committed operation is protected from a late automatic rollback. Back up active
witness data for later disaster recovery. Root filesystem damage, loss of the host
itself, revoked SSH/sudo access or missing backups still require host recovery.

## Docker to native, and image refresh

Expand **Docker witness: native conversion and image update**, select the operation,
then **Review operation**. The table includes the current image/version, CA and
all attached clusters. **Apply reviewed operation** requires the witness name.

Native conversion installs the native qnetd package under a temporary runtime unit
mask, so package scripts cannot start a second listener. The current Docker NSS
copy is checked with native certutil before switchover. The stopped original
container and private database snapshots are retained. After all votes are proven,
the native unit is enabled and the old Docker data is archived under the operation
journal. A later reviewed native-to-Docker conversion remains possible.

Image refresh rebuilds only the fixed in-repository Debian recipe, with fresh base
and package downloads. Arbitrary image URLs and shell snippets are not accepted.
The candidate's exact image ID and qnetd package version are recorded. An isolated
container validates an NSS copy before replacement. The old container/image and
pre-update database stay available for recovery. After successful commit, the
verified image also becomes the managed recipe tag, so later native-to-Docker
conversions reuse the refreshed image rather than the older cached recipe image.

Both operations use an independent 180-second rollback timer, preserving the CA.
**Recover original witness** restores an unfinished operation and verifies all node
votes. Journals/backups reside in `/var/lib/roxy-wi/qnetd/lifecycle/<id>`.

## Move host or rotate CA

Expand **Move witness to another host or rotate its CA**. For a host move, install
the independent target witness first using the same installer, then select it.
The target must have no connected or assigned clusters. Alternatively choose
**Rotate CA on current host**, which generates a fresh CA locally.

**Review witness trust change** displays both CA identities, every included cluster
and client, configuration changes and recovery behavior. Every cluster served by
the source must be registered in the active group, healthy, online and quorate.
**Apply reviewed trust change** requires the source witness name.

Each node generates its own new client private key locally. Only the public CA,
CSR and signed certificate pass through the controller. A source CA private key
is never copied to the target. A target CA is preserved for a host move; rotation
creates a new CA on the same host. Certificate databases are prepared privately
before any qdevice client is stopped.

All clients stop before source retirement and target activation. Custom Corosync
transport/comments are preserved: a host move replaces only the unique
`quorum.device.net.host` scalar. The files are syntax-checked before switching.
After all TLS votes are verified, the old remote witness stays disabled/stopped,
and the registration points to the target. Workloads and cluster daemons continue
running throughout this witness-only change.

### Failure and recovery

The candidate host has an independent 180-second recovery timer. Client timers
restore their private backups after 195 seconds. Same-host rotation restores the
original CA; its clients reconnect to the original witness.

For a **remote host move**, the target timer stops/disables the target. Client
timers restore the old files and leave qdevice stopped. The original remote source
stays stopped: it is deliberately not restarted independently while the state of
the other arbiter is unknown. With both cluster nodes healthy the cluster keeps
its ordinary node votes; the external vote can be temporarily unavailable.

Review again and select **Recover original trust**. The queued recovery verifies
both host identities and every node identity, reaches and confirms the target is
stopped, restores client files, then starts the source and its clients and checks
all votes. If the target is unreachable, source reactivation is refused. This
fail-stop order prevents two independent witness authorities from being active
for the same cluster after an uncertain distributed change.

Pending trust changes block other mutating cluster jobs. Public journal state and
recovery are accessible through the installer; private host/client snapshots are
under `/var/lib/roxy-wi/qnetd/trust/<id>` and
`/var/lib/roxy-wi/qdevice-trust/<id>`. Committed changes require a new reviewed move
or rotation rather than an automatic rollback. Custom qnetd listener arguments,
unknown clients, drift, inaccessible hosts and invalid certificates are refused.
