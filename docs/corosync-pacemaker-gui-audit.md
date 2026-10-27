# Corosync/Pacemaker GUI and component audit

Audit date: 2026-10-27. The comparison uses the current Roxy-WI Installation,
service navigation/templates and shared `ui-components.css`/jQuery UI widgets.
It does not certify every third-party agent, workload or distribution.

| Area | Result / implemented correction |
| --- | --- |
| Navigation | Standard Services submenu, separate Overview/Resources/Config/Quorum/Logs/Monitoring/Versions routes, retained cluster selection; installer remains under Installation. |
| Fields and actions | Existing input/checkbox/select macros, jQuery UI widgets, `rw-button`, `rw-form-field`, `rw-table-toolbar` and shared confirmation dialogs. No Pacemaker-specific stylesheet or inline layout overrides. |
| Installation | Separate new/adopt/witness modes; the requested mode is visible on first render. Docker uses the same checkbox component as existing service installers. |
| Witness conversion | Reviewed source/CA/cluster table, typed confirmation, durable operation state, host rollback timer, GUI recovery and logs. Host selection and action toolbar are separate rows to avoid a crowded wrapping row. |
| Membership | Replaced required hand-written JSON with the same node table used for registration: existing identities are fixed; new nodes use registered servers and discovered host addresses. JSON remains read-only reference. |
| Agent selection | Genuine selector, filtering, installed-on-all-node checks, per-class counts and explanation that availability is not a running service. Required/optional fields and operation timings come from native metadata. |
| Packages | Enabled-repository candidate/installed versions per node, repository refresh and reviewed installation/update through Operations. |
| Resources/constraints | GUI-generated drafts, real resource/node/removal selectors, validation/simulation and confirmation before application. Runtime controls use standard action menus. |
| Advanced configuration | Complete CIB editor remains inside the web UI for schema-supported advanced rules, bundles, operations and fencing topology. It is an advanced text editor, not a separate graphical wizard for every XML feature. |
| Diagnostics/history | Node journals, all-node quorum diagnostics, witness logs, encrypted history and restore-as-draft are available through web controls. |

The normal supported workflows above do not require opening a server terminal.
Servers/credentials, compatible OS/packages, network reachability and external
repositories/entitlements remain prerequisites. Installing an agent does not deploy
its application, configure external storage/hardware or supply device credentials.

## Advanced integrations

| Workflow | GUI and implementation |
| --- | --- |
| Exporter | Installation / Monitoring uses the existing exporter installer, Operations/Ansible and native controls. Version, listener, real metrics and Prometheus target are visible in the same page. |
| Auto Start | Monitoring reads/applies native systemd restart policy on every cluster member. Conflicting independent proxy Auto Start is coordinated; applications stay under Pacemaker. |
| Reverse witness conversion | Reviewed Docker-to-native conversion preserves CA and validates the copied NSS database before stopping the container. |
| Image refresh | Rebuilds the fixed repository recipe, checks the candidate database offline, retains the previous container/image and checks every TLS vote before commit. |
| Witness host / CA | Installer contains target selection, CA rotation, public certificate enrollment on every node, durable review/recovery and explicit fail-stop handling of interrupted remote moves. |
| Adopted/custom transport | Quorum contains before/after review, quiesce, confirmed maintenance migration, recovery and explicit workload resume. |

The standalone subscription-distributed proxy keep_alive binary is not part of this
repository. Cluster daemon recovery uses systemd; this is separate from Pacemaker's
application recovery and from the internal health-notification workflow.

Arbitrary application deployment, external storage/hardware configuration and every
possible agent-specific fencing topology are not inferred automatically. The web
CIB editor remains available for schema-supported advanced configuration. See the
[control reference](corosync-pacemaker-controls.md),
[migration guide](corosync-pacemaker-witness-migration.md),
[transport maintenance](corosync-pacemaker-transport-migration.md),
[monitoring guide](corosync-pacemaker-monitoring.md) and
[verification record](corosync-pacemaker-verification.md) for exact coverage.

## Browser layout checks

Installation/Monitoring exporter controls, member tables, planned transport review
and native daemon policy tables were inspected in the browser. Actual 750/850-pixel
viewport overrides were measured on the active preview tab and reset afterward.
The document itself did not overflow. Member tables use the shared internal
horizontal scrolling container when needed. Exporter version cells now show the
short version, retaining full build metadata in the detail/tooltip; the table uses
the same structure as the other exporters. No new stylesheet was added.
