# Agents, native metadata and host discovery

An agent is the adapter Pacemaker calls to start, stop and monitor a specific
resource, or to fence an unresponsive node. Discovery counts available adapters,
not running services: OCF scripts, installed systemd units and STONITH device
drivers all contribute. A package can ship many drivers for hardware you do not
use. A discovered agent becomes active cluster configuration only when you create
a resource and apply its reviewed draft. The GUI shows counts by class.

Examples: `ocf:heartbeat:IPaddr2` manages a virtual IP, `systemd:haproxy` wraps an
installed systemd service, `stonith:fence_pve` controls Proxmox fencing and
`ocf:heartbeat:Dummy` is a test resource. Installation/metadata availability is not
a guarantee that an application, device credential or storage layout is ready.

Use **Services → Corosync / Pacemaker → Resources**. These controls require
cluster service access and an operator role; targets remain scoped to the active
group and existing SSH credentials. The controller does not need agent binaries
or a native package manager: commands run on the managed hosts.

## Discover and choose an agent

Opening **Add a resource or fencing device**, or selecting **Discover agents**,
queries native Pacemaker tools on every registered member for OCF providers,
STONITH agents and systemd units. Use the filter to narrow the real selector.
Only IDs present on every node can be selected. The agent manager shows node
counts and read failures; an unreachable node is not treated as proof of availability.

Selecting an agent reads its metadata on all nodes. The form generates required
and optional fields, descriptions, declared choices and default hints. Optional
fields are collapsed. Password/token fields are masked and their metadata defaults
are not returned. Known native OCF DTD declarations are accepted without loading
external DTDs/entities; labels and descriptions are rendered as text.

Start, stop and monitor timeouts and the monitor interval are suggested from
metadata. Values remain editable and are saved into the reviewed CIB draft.
Agent defaults are hints, not automatically copied values: native defaults can
include a path calculated for a resource ID or a particular host. Leaving a field
blank omits it so the agent evaluates its own default at runtime.

Required parameters must be compatible across the members. Options are limited to
shared choices; incompatible required fields/options require aligning packages.
Fencing forms also provide Pacemaker host-check/list/map fields. **Use registered
node names** fills the known cluster names; outlet IDs, VM IDs and credentials
remain explicit device configuration. Metadata is not a test of actual fencing.

**Advanced parameter overrides (JSON)** is optional for extra settings and overrides
normal fields. Operators can still use the complete CIB editor for advanced
operations, per-node expressions, bundles and other settings outside the form.
A rescan or agent change resets dynamic parameter fields; review before saving.

## Install or update agent packages from the web

1. Open **Agents and repository packages**.
2. Select **Read repository packages**. This reads the hosts' existing native
   caches; use **Refresh repositories** to queue apt/DNF metadata refresh first
   when necessary.
3. Filter and select a package. Review installed → candidate versions for every node.
4. Select **Install / update on cluster nodes**, review the affected package and
   versions, and type the cluster name to confirm.
5. Wait for Operations, then rescan. Newly installed agents appear in the selector.

Package selection is restricted to `resource-agents*` and `fence-agents*` names
actually present in the enabled native repositories on all members. It does not
accept an arbitrary shell command, URL, package-manager option or script upload.
The reviewed candidate digest is checked when queuing and again in Operations.
Targets, credentials, group membership, service access and operator permission are
also rechecked. Each node installs its exact reviewed version, verifies the installed
version afterwards, and records an audit event. The known fence_pve packaging
repair is applied when needed after a package change.

Native dependencies may be installed/updated. Apt transactions refuse package
removals. A package job is serialized with other Roxy-WI cluster operations but
cannot make a multi-node package transaction atomic. On failure, earlier nodes
may already have completed: inspect the task, reread the package plan and rescan
before queuing another reviewed operation. Interrupted writes are not automatically
replayed and there is no automatic package rollback.

The workflow does not enable repositories/entitlements, upgrade the OS, configure
new resources, infer device credentials or perform a fencing action. Use trusted
enabled native repositories. Installing an OCF container agent does not install or
configure its container runtime/image; existing proxy service installation is
available through Roxy-WI's Installation workflows. Custom vendor agents can be
discovered if already installed, but their external installers are not executed by
this package workflow.

## Other fields populated from hosts/cluster state

| Data | How it is obtained / used |
| --- | --- |
| Actual node hostname and FQDN | Read over SSH after selecting a server for a new cluster; the actual short hostname is prefilled. |
| Corosync address choices | Read global non-loopback, non-link-local IP addresses with interface names/prefixes. Choose the intended network explicitly, or enter an intentional custom IP/DNS name. |
| Existing cluster/witness services | Read systemd active state; an already active cluster/witness host is not presented as an empty new node. |
| Planned node IDs | Assigned from unused IDs in the registration form; editable and validated for uniqueness. Existing-cluster discovery reads actual IDs. |
| Resource/wrapper/constraint IDs | Read the current CIB on the controller and return IDs/types only, without parameters or resource passwords. Used for constraint/removal selectors. |
| Node choices for location constraints | Read registered membership, instead of manually typing a node name. |
| Agent required fields, choices, hints and timings | Read installed agent metadata on every node; no hard-coded list of example agents is used as proof of availability. |

Cluster names/descriptions, the desired VIP/network, service dependencies,
placement policy, scores, fencing targets/credentials and application-specific
values express the operator's intent. They cannot be safely inferred from the
fact that an address, disk, service or agent happens to exist on a host.

An installed/discovered agent is not a vendor certification or a guarantee that a
particular workload is configured correctly. Validate/simulate and verify its
runtime behavior, especially fencing and application/storage dependencies, using
the [control reference](corosync-pacemaker-controls.md) and
[verification scope](corosync-pacemaker-verification.md).
