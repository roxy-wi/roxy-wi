# Corosync and Pacemaker

Open **Services → Corosync / Pacemaker**. This module manages a cluster as one
configuration domain while reusing Roxy-WI server registrations, SSH credentials,
groups, Operations workers, RabbitMQ and notification routing.

The live-qualified targets are Debian 13 (Corosync 3.1/Pacemaker 3.0) and Rocky
Linux 9.8 (Corosync 3.1.10/Pacemaker 2.1.10, SELinux enforcing). Roxy-WI
itself should run on its supported Python 3.10–3.12 runtime. Other target
distributions and older Pacemaker output schemas need separate qualification.
See the [platform and deployment matrix](ha-support.md) for implemented apt/dnf
profiles, Docker workflows, HA technology selection and SYN-flood settings.

## Access and installation

**Installation → Corosync / Pacemaker** provides separate entry points for a new
Linux cluster, adoption of a running installation, and a standalone quorum witness. The installer is separate from the service management pages and uses existing
Roxy-WI form controls.

HA cluster service permission (service ID 5) controls access. Operators at role
levels 1–3 can configure clusters. The shared Installation landing page/menu
retains its existing administrator restriction (levels 1–2); the dedicated
`/install/pacemaker` workflow allows cluster operators (levels 1–3). Viewers can see status and history, but cannot
read CIB snapshots, journals or credential-bearing configuration.

First register physical server entries and their SSH credentials in the active
Roxy-WI group. Nodes need Python 3.8 or newer available as `python3`, SSH access and non-interactive sudo. Use the
actual Corosync `cluster_name` for an existing cluster; node names must match the
managed host names for provisioning. Corosync addresses can be on a separate
cluster network. Registration alone changes no remote configuration.

For an existing installation, choose **Adopt an existing cluster**, select one
running node, and inspect the discovered cluster name, members, resources and
quorum. Map every member to an enabled server in the active group. IP and DNS
Corosync addresses and FQDN node names are supported. Each mapped node must be
reachable with running Corosync and a readable Pacemaker CIB. Discovery requires
a Corosync nodelist with 2–32 nodes and the standard configuration file path.

Adoption rechecks the reviewed topology and CIB digest, verifies each SSH target's
local Corosync node ID and requires all mapped nodes to report the same cluster
configuration. It writes only Roxy-WI registration, audit state and an encrypted
initial CIB/Corosync snapshot. It does not reinstall packages, restart services,
change resource/fencing definitions, replace authentication keys or modify quorum.
Already registered clusters cannot be registered again.

Adopted clusters retain their custom Corosync transport and qdevice settings.
CIB management, node/resource actions, diagnostics and monitoring are available.
Managed Corosync membership/witness changes and bootstrap are blocked for adopted
clusters. An explicit transport/certificate migration is required before using
Roxy-WI's generated membership configuration; there is no automatic conversion.

For a new cluster, open **Installation → Corosync / Pacemaker → Install cluster**.
Choose **Register cluster**, enter its name and at least two distinct servers,
then enter each actual node hostname, Corosync address and unique positive node ID.
Use **Add member** or **Remove** to adjust the planned membership. **Cancel** closes
the form without registering it. **Save registration** stores the plan only.
Select that registration, choose **Check target platforms**, optionally enable
**SYN-flood protection** and **Install Proxmox fencing agent**, then select **Install cluster on empty nodes** and type
the cluster name in the confirmation dialog. Cancelling this dialog does not
queue installation. Operations checks *all* nodes before modifying any, installs the
native distribution packages, distributes a shared random authentication key and encrypted
knet configuration, starts the services, and waits for quorum and online nodes.
It refuses Proxmox hosts, active cluster services, an existing CIB or an existing
Corosync authentication key. Fencing remains enabled by default; configure an
appropriate fencing agent before relying on automatic resource recovery.

Web, Scheduler and Operations must all run. Scheduler publishes durable operation
tasks to RabbitMQ; Operations performs SSH work. A queued task remaining in
`created` or `published` is an Operations/queue health issue, not a completed
cluster operation. Package installation also needs access to the distribution's enabled HA repositories.

See the [control reference and recovery procedures](corosync-pacemaker-controls.md)
for every page, form field, runtime action and operational failure state.

## Resources and changes

The resource form discovers OCF, systemd and STONITH agents from all members.
Its selector includes only agents found on every node. Native metadata supplies
required/optional parameter fields, default hints and operation timings.
The same page installs/updates available native agent packages through reviewed
Operations tasks. See the [agent/package guide](corosync-pacemaker-agents.md).
Forms support groups, clones and promotable clones. Constraint forms cover location,
mandatory ordering and colocation. Cluster properties and removal forms also
produce drafts. The complete CIB editor retains advanced rules, resource sets,
agent operations, fencing topology, bundles and other schema-supported options.

1. Save a draft or create one through a form.
2. Validate and simulate it. Inspect the previous/proposed configuration and
   the scheduler simulation.
3. Apply the reviewed change. The worker checks quorum, rechecks the configuration
   digest and commits a versioned Pacemaker patch.

Concurrent changes by another Roxy-WI worker, `pcs`, `crmsh`, or an administrator
invalidate a stale draft/patch. Runtime status updates alone do not invalidate
the configuration digest. A failed SSH write is never replayed on another node.
An interrupted or uncertain apply becomes `unknown` and requires inspecting the
cluster before creating another reviewed change.

History can restore a CIB snapshot **as a new draft against current state**.
It does not force a stored CIB back into the cluster. Snapshots and simulations
are encrypted with Roxy-WI's Fernet key; credential-key rotation includes them.
Back up both the application database and its encryption key.

Node controls provide standby/online. Resource controls provide enable, disable,
restart, cleanup, move and clear. Moving installs a Pacemaker location preference;
**clear** removes that temporary preference. Maintenance controls affect the whole
cluster. Operations are audited, including their user and resulting state.

## Corosync and quorum

A two-node registration shows an explicit recommendation to use an independent
quorum witness and configure fencing. A running cluster shows the actual qdevice
vote: available, configured but not voting, absent, or not verifiable. The
absence of a witness is a design warning, not a claim that Corosync two-node mode
cannot operate. A witness does not replace fencing.

**Installation → Corosync / Pacemaker → Install witness only** installs and enables
`corosync-qnetd` on a separate registered supported Linux host through Operations.
Select **Runtime: Docker** or **Podman** for a managed standalone container; choose **Native** for native
packages/systemd. See the [Docker witness guide](corosync-pacemaker-witness-docker.md)
for engine prerequisites, persistent CA storage and recovery. It does
not install Pacemaker or turn the host into a cluster member, and it does not
attach a cluster automatically. Existing witness CA/certificates are preserved.
The selected server must not belong to any registered cluster or run active
Corosync/Pacemaker services; Proxmox hosts are refused.

The Roxy-WI host can provide qnetd when it is independent of the cluster members
and has an enabled server entry with SSH credentials. **Select Roxy-WI host**
selects an entry whose IP/name matches the browser's application hostname; behind
a reverse proxy, select the actual registered host explicitly. Keep the witness
in a failure domain independent of both nodes and allow their TCP 5403 access.
The web application's availability itself does not provide a vote: qnetd is a
separate system service or managed Docker container and continues independently of the Roxy-WI web process.

Diagnostics read the configuration and quorum state of every registered member.
Membership changes have their own encrypted drafts, validation and history.
They require every current member online and quorum. Existing node names, IDs
and addresses remain fixed during online membership updates.

To add a node, load current membership and choose **Add member** in the node table.
Select its registered server and discovered Corosync address. Existing member
identities remain read-only; remove a drained/standby member with its row action.
The JSON view is read-only reference. The
worker checks and provisions it with the existing authentication key before
reloading membership. To remove a node, first put it in standby and wait until
its resources have drained. The worker stops and disables its cluster services,
reloads the remaining membership and removes its Pacemaker node record.

Membership changes regenerate the managed knet configuration. Review that entire
file when importing a cluster with custom Corosync settings. This workflow does
not preserve arbitrary custom transport blocks, and it does not implement online
renumbering or address changes. Removed nodes retain their authentication key
and local CIB; explicitly inspect/reset them before provisioning them again.

Select a separate supported Linux host as a net qdevice witness. The worker installs
qnetd/qdevice, distributes CA and cluster certificates over SSH, requires TLS,
and extends certificates to added nodes. The generated quorum configuration
switches between two-node handling and a qdevice as appropriate. Migrating an
existing witness's CA requires an explicit certificate migration; selecting a
different witness while one is configured is refused.

Corosync file updates are staged and validated before commit. A network loss
during a coordinated multi-node commit may leave partial changes. Such an apply
is marked `unknown`; use the stored previous configuration and node journals to
reconcile it. No automatic rollback or forced quorum adjustment is performed.

## Monitoring

Monitoring is opt-in per cluster. Scheduler queues a check at most once a minute
when no other operation is pending. Checks distinguish unreachable clusters,
lost quorum, unavailable/unclean nodes and failed/blocked resources. Health changes
enter history and the existing durable notification outbox. Repeated unchanged
states produce no additional notifications; recovery produces one notification.
A configured qdevice losing its vote is reported as `witness-unavailable`, even
when the two cluster nodes still have quorum.
Delivery uses the existing HA cluster alert routing for the first registered
server and its group. WebSocket availability and external channels depend on the
normal Roxy-WI notification deployment and configuration.

## Internal HTTP API

Every endpoint requires the normal JWT session/token. Browser writes require its
CSRF token. IDs and every member are scoped to the active group.

Deliberate input errors retain their client-safe validation messages. Unexpected
value/parsing errors and SSH failures return generic HTTP 400/502 responses;
exception text, tracebacks and command output are not copied into the API error.
Inspect the authorized application/node diagnostics for operational failures.

| Endpoint under `/pacemaker/api` | Purpose |
| --- | --- |
| `GET /`, `POST /` | List/register clusters |
| `GET /servers/<server>/facts` | Read hostname, FQDN, network addresses and active cluster/witness services; operator only |
| `GET /<id>/agents` | Discover per-node agent IDs and verify availability across all members |
| `GET /<id>/agents/metadata?agent=...` | Read shared parameter/action metadata; operator only |
| `GET /<id>/agents/packages` | Read enabled-repository agent packages and per-node version plans |
| `POST /<id>/agents/packages` | Queue package install/update with `package`, `plan_digest` and cluster-name `confirm` |
| `POST /<id>/agents/repositories` | Queue native repository metadata refresh with cluster-name `confirm` |
| `GET /<id>/choices` | Secret-free resource/wrapper/constraint IDs and node choices |
| `GET /servers` | Enabled physical servers in the active group |
| `GET /platform/<server>` | Detect the native installation profile and its qualification status |
| `POST /discover` | Read a running cluster from `server_id`; no CIB secrets in the response |
| `POST /adopt` | Verify reviewed membership, mapped servers and digests; save registration only |
| `POST /witness/install` | Queue qnetd-only installation on `server_id`; optional `container_engine` selects `native`, `docker` or `podman`; the legacy strict boolean `docker` defaults to false; no cluster registration required |
| `GET /witness/<server>` | Read native/Docker mode, qnetd status, package version and CA fingerprint |
| `GET /witness/tasks/<task>` | Read a group-scoped witness installation task |
| `DELETE /<id>` | Remove registration only; refuse while work is active |
| `GET /<id>/status` | Structured cluster state |
| `GET /<id>/config` | CIB and configuration digest; operator only |
| `POST /<id>/build` | Resource/constraint/property/removal draft |
| `POST /<id>/changes` | Complete CIB draft with `xml` and `base_digest` |
| `GET /<id>/changes/<change>` | Review encrypted snapshot contents |
| `POST /<id>/changes/<change>/validate` | Queue validation/simulation |
| `POST /<id>/changes/<change>/apply` | Queue reviewed application |
| `POST /<id>/changes/<change>/restore` | New CIB restoration draft |
| `GET /<id>/corosync`, `POST /<id>/corosync` | Diagnostics / membership draft |
| `POST /<id>/bootstrap` | Queue provisioning; `confirm` must equal cluster name, optional strict booleans `syn_flood` and `fence_pve` default to false |
| `POST /<id>/actions` | Queue a typed node/resource action |
| `PUT /<id>/monitor` | Set `enabled` to a boolean |
| `GET /<id>/history` | Events, change states and active task |
| `GET /<id>/tasks/<task>` | Group/cluster-scoped operation progress |
| `GET /<id>/logs/<server>` | Bounded node journal; operator only |

Writes that execute remote work return HTTP 202 and a task ID. Read task progress
until `completed` or `failed`. This API does not accept arbitrary shell commands.

## Verification

Unit/security tests cover group and service isolation, viewer restrictions,
untrusted XML, configuration digests, encrypted history, key rotation, locks,
duplicate operations, interrupted writes, monitoring and form builders.

The Debian and Rocky VM qualifications exercised bootstrap, VIP/Dummy resources, ordering
and colocation, validation/simulation/commit, move/clear, standby/online, qdevice
TLS, adding/removing a third member, and a real Proxmox fencing restart. The lab
fencing account was restricted to disposable test VMs and its denial of access to
the protected VM was verified before the fencing test.

A fresh Rocky host also exercised the native package transaction with optional
Proxmox agent installation, automatic packaging repair, original-file backup,
metadata verification and Corosync syntax validation. See the
[verification record](corosync-pacemaker-verification.md).

Live adoption qualification also compares each node's CIB digest and Corosync
file before and after adoption, confirming that the existing cluster is unchanged.

The online editor and database remain the source of configuration/audit state;
no new host-specific cluster facts or credentials belong in the source tree.

## Design boundaries

The module keeps Pacemaker CIB transactions separate from coordinated Corosync
file changes. This avoids treating a replicated cluster database as independent
per-server configuration files. The common Operations queue handles long work
without tying it to a web request. Per-cluster database leases serialize work,
and versioned CIB patches provide concurrency control against external managers.

The Corosync project recommends qdevice for even-sized clusters, especially two
nodes: <https://github.com/corosync/corosync-qdevice>.

The current design targets small and medium clusters (2–32 members). Revisit
parallel health collection, snapshot/event retention, richer per-node recovery
records and additional Corosync transport profiles before managing a large fleet.

## Advanced workflows and monitoring

Use the versioned guides for [witness conversion, image refresh, host moves and CA
rotation](corosync-pacemaker-witness-migration.md), [planned adopted/custom transport
migration](corosync-pacemaker-transport-migration.md), and [exporter installation
and daemon Auto Start](corosync-pacemaker-monitoring.md). Each workflow exposes its
review, confirmation and recovery in the web UI. The existing CIB editor remains
available for advanced schema-supported Pacemaker configuration.

Additional operator APIs:

- `GET/POST /pacemaker/api/witness/<id>/lifecycle/{native|image-upgrade}`;
  `POST .../lifecycle/recover`.
- `GET /pacemaker/api/witness/<source>/trust/<target>?rotate=0|1`;
  `POST .../<source>/trust` and `POST .../<source>/trust/recover`.
- `GET/POST /pacemaker/api/<cluster>/transport`; `POST .../transport/{quiesce|recover|resume}`.
- `GET/POST /pacemaker/api/<cluster>/autostart`.
- `POST /install/exporter/ha_cluster`; `GET /install/exporter/ha_cluster/status/<member-ip>`.

Mutations use JWT/CSRF, typed host/cluster confirmation and/or a reviewed digest as
shown by their GUI. Queued mutations return an operation identifier; inspect its
terminal status rather than assuming acceptance means completion.

Podman component and witness workflows, including their pending VM qualification,
are documented in the [managed component guide](managed-containers.md).
