# Corosync/Pacemaker control reference

This reference describes the Corosync/Pacemaker module added in this change.
For access, adoption semantics and API endpoints, see the
[administration guide](corosync-pacemaker.md). Consult the
[platform matrix](ha-support.md) before installation and the
[verification record](corosync-pacemaker-verification.md) before deployment.

## Navigation and common controls

Services → Corosync / Pacemaker has separate pages, not scroll anchors.
The **Cluster** selector carries the selected registration between service pages.
**Refresh** reads status and history; it does not apply configuration. A failed
status read leaves installation and discovery available. **HA technology** opens
the Keepalived or Pacemaker management workflow; it does not convert a cluster.

| Page | Controls and effect |
| --- | --- |
| Overview (`/pacemaker`) | Quorum, coordinator, node state and resources. Per-row action menus execute the runtime actions below after confirmation. |
| Resources (`/pacemaker/resources`) | Discover installed agents and repository packages, install/update agent packages, and use metadata-driven resource forms and discovered constraint/removal choices. Successful forms open Config with the new draft selected. |
| Config (`/pacemaker/configuration`) | Load current CIB, save draft, compare previous/proposed configuration, validate/simulate and apply a reviewed change. Loading reads configuration that can contain credentials. |
| Quorum / witness (`/pacemaker/quorum`) | Read all nodes; load and review managed membership, token timeout and independent qdevice server. Saving creates a draft and opens Config. |
| Logs (`/pacemaker/logs`) | Select a member and read at most 200 journal lines from Corosync and Pacemaker. |
| Monitoring (`/pacemaker/monitoring`) | Enable/disable periodic monitoring and cluster-wide maintenance. Monitoring uses existing HA notification routes; maintenance changes resource management. |
| Versions (`/pacemaker/history`) | Change state, review, restore a previous CIB as a fresh draft, task state and audit events. Restore never applies automatically. |
| Installation (`/install#pacemaker-installation`) | Install cluster, adopt existing cluster or install witness only. Each opens its dedicated installer mode. |

Viewer roles can read Overview, Resources and Versions but have no mutation
controls or secret-bearing review/configuration/journal access. Configuration,
quorum and monitoring pages require an operator. Every server and change is scoped
to the active group; changing groups does not grant access to another group's data.
The shared Installation landing page/menu retains its existing role 1–2 restriction;
cluster operators at role 3 can use the dedicated `/install/pacemaker` workflow.

## Installation forms

| Mode / control | Required input and outcome |
| --- | --- |
| New cluster → Register cluster | Cluster name (letter first; letters, numbers, `_`, `-`; max 63), optional description, 2–32 enabled server entries. Each node has a distinct server, hostname read from the host, an explicitly selected Corosync IP/DNS address and an unused positive node ID. Active cluster/witness services are identified before registration. Save records the plan; it does not install anything. |
| Check target platforms | Read OS/profile and live qualification status for all selected nodes. It does not guarantee package repository availability or firewall reachability. |
| SYN-flood protection | Optional new-installation TCP settings, off by default. Exact values and rollback limits are in the platform guide. It is not Corosync UDP protection or general DDoS protection. |
| Install Proxmox fencing agent | Optional native agent package and metadata check. Repairs the known EPEL library placeholder with an original-file backup. Requires available agent packages (EPEL on EL); device configuration and hypervisor permissions remain separate. |
| Install cluster on empty nodes | Type the selected cluster name to confirm. All nodes pass emptiness/identity checks before any package installation. Existing CIB/config/authkey or active cluster services cause refusal. |
| Adopt existing cluster → Discover cluster | Select one running node. Review discovered name, quorum and membership; map every node to its matching Roxy-WI server. Adopt verified cluster reads all nodes again and registers only if the reviewed topology/configuration still matches. |
| Quorum / witness → Review migration / Convert to Docker / Recover native witness | Guided native conversion with preserved CA, per-node vote checks and independent host rollback timer. See the [migration guide](corosync-pacemaker-witness-migration.md). |
| Quorum / witness → Use Docker | Installs a separate managed qnetd container on the selected SSH host. Defaults to native packages. Existing native/Docker witnesses are not automatically migrated. See the [Docker witness guide](corosync-pacemaker-witness-docker.md). |
| Quorum / witness → Select Roxy-WI host | Select an eligible registered server matching the application's hostname/IP. Behind a reverse proxy, choose the actual independent host explicitly. |
| Check platform / Read status | Inspect the selected witness host, package version, service state and public CA fingerprint. |
| Install witness only | Confirm the exact independent host. Install/enable qnetd without Pacemaker or cluster membership. Initialize a new NSS database only when none exists; preserve existing CA/certificates. Attach it separately under Quorum / witness. |

Selecting another installer mode does not install, adopt or attach anything.
After saving a registration, verify the Cluster selector before provisioning.
An existing registration can be opened directly with
`/install/pacemaker?setup=new&cluster=<id>`. Discovery rejects duplicate adoption.
Deleting a registration through the API unregisters it only; it does not uninstall
the remote cluster. There is no remote cluster destruction button.

## Resource and configuration forms

Open **Add a resource or fencing device** to discover agents on every node.
Filter the list, select an installed agent, and fill the required fields generated
from its metadata. Optional fields are collapsed. IPaddr2 asks for the intended VIP;
Dummy can use its native defaults. The controller rechecks availability and required
parameters before saving a draft. See the [agent/package guide](corosync-pacemaker-agents.md).

Agent defaults are shown as hints and omitted when left blank; paths computed for
a particular resource instance must not be copied from a metadata example.
**Advanced parameter overrides** is an optional JSON object with string values.
Its keys override the generated fields. Normal agent parameters do not require
handwritten JSON. Runtime/application installation is separate from an OCF or
fencing script package; existing Roxy-WI Installation workflows handle proxy services.

| Form field | Meaning |
| --- | --- |
| Resource ID | Unique XML ID; letter/underscore first, then letters, numbers, `_`, `.`, `-`. |
| Agent | Select a discovered ID: `ocf:<provider>:<type>`, `systemd:<unit>` or `stonith:<agent>`. Examples: `ocf:heartbeat:IPaddr2`, `systemd:haproxy`, `stonith:fence_pve`. Only agents installed on every registered node can be selected. Metadata is read and checked on every node; missing agents are installed through Agents and repository packages. |
| Parameters | Metadata-generated required and optional fields, with per-agent descriptions and default hints. Fencing passwords become part of the CIB; only operators may load it. |
| Monitor interval | Duration such as `30s`, `500ms`, `5min` or `1h`. The initial interval and start/stop/monitor timeouts come from native metadata and remain editable. Advanced operation roles/depths belong in the CIB editor. |
| Start / Stop / Monitor timeout | Read the recommended values from agent metadata; explicit values are included in the CIB draft. |
| Container | Standalone, Group, Clone or Promotable clone. Group/clone ID is required for a wrapper. Creating a wrapper creates a new wrapper with this resource; use the CIB editor to extend existing groups/clones or set promotion rules. |
| Constraint Type | Resources and destination nodes are loaded from the current cluster. Location binds a resource to a node with Score; Order defines mandatory first → then ordering; Colocation uses the second resource and Score. |
| Score | Signed integer, `INFINITY` or `-INFINITY`; used by location/colocation. Order always uses mandatory ordering. |
| Property / Value | Pacemaker cluster property; validation checks the candidate. A form does not substitute for checking the property's semantics for the installed Pacemaker version. |
| Removal ID | Select an existing primitive, group, clone, bundle or constraint from the current cluster. Removing a wrapper removes its contained resources. Dependent constraints are not automatically removed; fix references in the CIB editor before validation. |

Each **Create draft** reads the current CIB/digest first. It neither deploys a
resource nor starts/stops services. For advanced operations, resource sets,
fencing topology, rules and bundles, use the complete CIB editor.

1. Review the previous and proposed configuration.
2. Select **Validate and simulate** and inspect the scheduler result.
3. **Apply reviewed change** is enabled only for a validated change; confirm it.
4. Wait for completion and verify the resulting status/resources.

Editing Candidate CIB XML clears the active review and disables Validate/Apply.
Save a new draft and validate that draft before applying edited XML.
Corosync drafts are generated from the Quorum form and cannot be saved as CIB XML.
There is no automatic retry of an uncertain write or rollback of resource actions.

## Runtime action menus

| Action | Effect / verification |
| --- | --- |
| Standby / Online | Set or clear a node's standby flag. Standby drains eligible resources and can interrupt them if no destination exists. Check resources before removing a member. |
| Enable / Disable | Set target-role Started/Stopped for the selected primitive or wrapper. Verify its final role; enabling still obeys constraints, quorum and fencing. |
| Restart | Ask Pacemaker to restart the selected resource/wrapper; dependencies can cause related changes. |
| Cleanup | Clear operation failure history and request re-evaluation/probes; this can permit a previously failed resource to start. |
| Move to node | Choose a node where the resource is not currently running and add a location preference for it. Constraints still apply. |
| Clear | Remove the temporary resource move/ban preferences. It does not delete administrator-defined constraints. |
| Enable / Disable maintenance | Set cluster-wide maintenance-mode. Enabling suspends normal resource management/monitoring; it is not a safe substitute for draining or fencing a node. Disable it explicitly when maintenance is finished. |

Menus for clone instances or bundle replicas target the enclosing managed
wrapper. All operations are queued and audited. **Cancel** in a confirmation
dialog queues no operation. A task completing means the requested command
completed; resource convergence may take longer. Check the resulting state.

## Managed Corosync membership and witness

Select **Load current membership** before editing. The member table shows each
registered server, cluster node name, Corosync address and node ID; keep existing
node identities unchanged. The current membership JSON is a read-only reference.
Token timeout is 1000–30000 milliseconds. A selected independent witness
adds a TLS qdevice vote; No net qdevice removes the managed qdevice configuration.
A witness does not replace fencing. The platform guide describes failure-domain
and TCP 5403 requirements.

Adding a member provisions an empty host. Removing one requires standby and no
resources on that member. All current nodes must be online and quorate. Review
the complete generated Corosync file, validate and apply the change under Config.
Every change must retain at least one current member; full membership replacement
is rejected during validation and checked again before applying any remote changes.
Replace nodes in separate reviewed changes instead. When a witness is selected,
application succeeds only after every resulting member reports the selected qnetd
address, active TLS and a witness vote. Overall cluster quorum alone is insufficient.
Failed verification leaves the change unknown; inspect node/witness diagnostics
and reconcile state before creating a fresh change.
This replaces the managed transport configuration; arbitrary imported transport
blocks are not preserved. Adopted clusters therefore have these controls disabled.
Use the [planned transport migration](corosync-pacemaker-transport-migration.md) and the separate [witness host/CA migration](corosync-pacemaker-witness-migration.md). Both expose review, confirmation and recovery in the GUI.

## Recovery and operational checks

| Symptom | Procedure |
| --- | --- |
| Task stays created/published | Check Scheduler, RabbitMQ and Operations role health and shared configuration/database/keys. Do not mistake queuing for completion. |
| No readable CIB | Verify SSH/sudo, node identity, service state and quorum on the nodes. Installation/adoption controls remain available. Restore access before saving new changes. |
| Validation fails | Review the proposed configuration and node logs; check installed agent names/parameters, missing resource references, fencing and the target's schema. Correct the draft and validate again. |
| Conflict / stale digest | An administrator/other manager changed configuration. Reload current state, create a fresh draft and review again. Runtime counters alone do not invalidate a draft. |
| Apply unknown/interrupted | Inspect all nodes and compare actual CIB/Corosync with the recorded previous/proposed state. Reconcile any partial change explicitly. Never replay an unknown apply blindly. |
| Bootstrap partially completed | Inspect each node's packages, services, authkey/config and CIB. Existing files intentionally prevent a blind reinstall. Reconcile or explicitly reset only disposable nodes; use adoption for an established cluster. |
| Witness unavailable | Check independent host status, TCP 5403, qdevice/qnetd journals, TLS CA/certificates and clock synchronization. A running qnetd alone does not prove an attached voting qdevice. Read actual quorum diagnostics. |
| Lost quorum / unclean node | Restore communication and confirm fencing and actual node state. Do not force expected votes or disable fencing to make status green. |
| Empty Resources page after bootstrap | Fencing stays enabled. Configure a working fence agent for every node and then create resources; inspect simulation and constraints. |
| Cannot add/remove adopted members | The module preserves imported transport. Use Quorum → Planned migration to managed Corosync transport. Review and quiesce before applying; the existing TLS witness is retained. |
| Monitoring enabled but no alerts | Confirm Scheduler dispatch and notification-outbox/channel setup, group/server HA alert routing, and an actual health transition. Repeated unchanged states are intentionally deduplicated. |

Before production use, back up the application DB and its Fernet key together,
plus node Corosync/authkey, CIB and witness NSS material through your normal secure
backup procedure. Keep credential-bearing backups access-restricted. Restoring
history creates a reviewed CIB draft; it does not recover missing witness keys,
transport files, application data or an unavailable controller database.

## Additional integrated workflows

| Control | Effect |
| --- | --- |
| Installation / Monitoring / Corosync-Pacemaker Exporter | Install fixed-checksum ClusterLabs exporter; show actual metrics and Prometheus target. |
| Monitoring / Auto Start for cluster daemons | Read/apply host systemd policies; coordinate conflicting proxy Auto Start. |
| Witness / Docker native conversion and image update | Review and execute reverse conversion or fixed-recipe refresh; recover original witness. |
| Witness / Move host or rotate CA | Enroll local client keys, switch trust with fail-stop recovery and verify every vote. |
| Quorum / Planned transport migration | Compare current/proposed configuration, quiesce, migrate, recover and explicitly resume nodes. |

See [monitoring](corosync-pacemaker-monitoring.md),
[witness migrations](corosync-pacemaker-witness-migration.md) and
[transport maintenance](corosync-pacemaker-transport-migration.md) for prerequisites,
exact effects, stored backup locations and failure behavior.
