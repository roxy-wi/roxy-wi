# Reviewed HA node maintenance

Open **Operations → HA clusters → Actions → Node maintenance** on the cluster card. This workflow manages registered cluster
resources and VIPs; it does not power off, reboot, patch or reinstall a machine.
It uses the existing **Premium Change Center** entitlement and Cluster service
permission. Every drain and return needs approval by another administrator.

## Workflow

1. Select the member, supply a change title and record evidence that the
   remaining nodes can carry the application load. A scheduler's placement
   prediction does not establish real application throughput.
2. Create the plan and select **Run drain checks**. This is a durable read-only
   Operations job. Inspect quorum, placement, identities and capacity evidence.
3. The plan lists eligible approvers: other enabled administrators in the same
   group with HA access. One of them opens the plan, reviews the check results and
   capacity evidence, and selects **Approve drain**. The author cannot approve
   their own plan. Once approved, select **Drain node** in the same dialog.
4. The worker rechecks permissions, approval, membership/SSH identities and the
   reviewed configuration before the write. It then waits for resource/VIP
   movement and established sessions on the detected VIPs to drain.
5. **Ready for maintenance** means registered resources and detected VIP sessions were observed
   drained. The node is handed over for the external maintenance procedure.
6. When the member is reachable and healthy again, select **Run return checks**.
   Review current placement and configuration and obtain a new independent
   approval using **Approve return**. **Return node** restores its eligibility/service and
   verifies the cluster. Resources need not move back to that particular node.

The dialog updates automatically, including approvals by another administrator.
The cluster card shows the active plan and its status. Completed and cancelled
plans remain in the dialog’s **History** tab, with older plans available on demand.
Closing the dialog does not stop an operation; reopening it restores current state.
Running checks again invalidates the previous approval. Change Center retains
the shared approval record and history; its details dialog also shows the checks
and allows approval. Checks and node actions are run from HA maintenance.

Protected servers require an administrator to execute the drain/return. Capacity
remains an operator assertion and is shown as such. Existing connections may keep
a node draining; a timeout never becomes a successful handover.

## Pacemaker

The review checks the remaining vote weight against the actual quorum threshold,
working TLS/witness votes when applicable, fencing enabled, cluster maintenance
mode off and managed active resources. The fixed helper simulates standby against
a private offline copy of the live CIB using crm_simulate and reads its resulting
crm_mon state. It refuses loss of a workload's last active instance or promoted
role and requires the selected node to be empty. Actual observations after the
write independently recheck the resulting resource state.

The only live eligibility write is crm_standby for the selected registered member.
The cluster remains reserved while a node is handed over: CIB/membership changes,
witness migrations, certificate deployments and other mutations using its common
lock must wait. Read-only status and health monitoring remain available. No
cluster-owned proxy is started/stopped independently.

Session drain covers static IPaddr/IPaddr2 addresses, including resolvable CIB
templates and attribute references. Conditional/unresolved VIP addresses are
refused. This does not prove application-level transaction completion or drain
arbitrary third-party resource agents' private protocols. Clone instance counts
may decrease during maintenance; the operator's capacity assertion must cover it.

Ordinary server-record changes for registered Pacemaker members use the same
durable cluster lock as maintenance enqueue and execution. Disabling, deleting,
or changing a member's identity returns HTTP 409 while maintenance is queued,
running or handed over. Both the selected node and its surviving peers remain
protected; ordinary edits resume after the approved return completes.

Membership registration/adoption, membership apply/removal and server-record
changes serialize discovery on the controller's shared `lib_path` storage before
acquiring provider locks. Contending writes return HTTP 409 promptly and can be
retried; unrelated read/status requests remain available. All controller workers
must use that same shared storage, as with existing HA maintenance lock files.

## Keepalived


Independent Keepalived Auto Start must be disabled. Every registered VIP must
initially have one owner and all members must be reachable. The worker freshly
checks every surviving member's service health before the mutation, then checks
again immediately before stopping the selected native Keepalived service. A dead
standby rejects the drain without stopping the last working member.

Before masking or stopping, the original native systemd startup policy is stored
in the encrypted durable plan journal. The worker creates and verifies a persistent
systemd mask (not a runtime mask), preventing automatic re-entry after an external
maintenance reboot. It verifies VIP movement and established VIP sessions before
handover; socket matching normalizes IPv4-mapped IPv6 endpoints as well as native
IPv4/IPv6 addresses. VIP movement can interrupt connections. This provides neither
VRRP quorum nor fencing.

Only a freshly reviewed, independently approved return removes the maintenance
mask and restores the recorded startup policy. Interrupted mask/restore requests
retain their durable intent and require reviewed recovery. Pre-existing masks and
unsupported startup-policy states are refused rather than adopted. Verify drain
also checks that the owned persistent hold is still present.

Automatic containerized Keepalived drains are currently refused because engine
restart policies and boot-start units do not yet have a verified durable hold.
Readiness observations remain supported. Container bindings are never silently replaced with native systemd management. Included custom Keepalived files require separate
configuration review before this automatic workflow can establish its scope.

Cluster/VIP mutations through the actual `/api/ha` API and shared service paths
use the same reservation lock as maintenance. Reservations also protect relevant
member/configuration/service mutations. Read-only operations remain available;
ordinary mutations resume after a completed approved return.

## Interrupted work and evidence

A failed or interrupted mutation is never silently replayed. The plan stays
unknown/draining and no handover is reported. Use **Verify drain** to re-observe
without repeating the write, or **Review return** for a new reviewed recovery.
The reservation cannot be cancelled after handover; it must be explicitly
returned. Member identity/configuration drift invalidates the earlier approval.
Private host errors are not included in plan events.

A successfully observed drain **and** return creates a configuration-bound
`planned-node-maintenance` record visible in HA readiness, with operation/plan
identifiers and both timestamps. Recovery after an unverified drain does not
create successful-test evidence. A planned maintenance result never establishes
fencing or network-partition safety; older configuration evidence is labelled
stale after drift.

## API and storage

Migration `20261028020000_ha_maintenance` adds encrypted plan state. Existing
Change Center records hold review/approval metadata and retain their normal
group isolation and self-approval restriction.

| Endpoint | Action |
| --- | --- |
| `GET /ha/api/maintenance` | Active-group plan history |
| `POST /ha/api/maintenance` | Create provider/cluster/node/title/capacity plan |
| `POST /ha/api/maintenance/ID/review` | Review drain |
| `POST …/drain` | Execute the approved drain |
| `POST …/verify` | Observe an uncertain drain without replay |
| `POST …/review-return` | Review a return/recovery and reset approval |
| `POST …/resume` | Execute the approved return |

Roles 1–3 may operate plans; protected-node writes and independent approvals need
roles 1–2. Mutations use existing JWT/CSRF. Worker permission and identity checks
apply again after queuing. HTTP 202 means queued, not completed.

## Verification boundary

Local tests use authenticated API/database/Chromium workflows and real offline
Pacemaker 2.1.6 CLI tools on isolated Ubuntu 24.04 ARM64. They cover approval,
quorum budget, surviving placement, handover/return, connection delays, failed
commands, drift, group/role changes, Keepalived takeover recovery and interruption
handling. The scheduler checks are part of GitHub's Linux integration job.
On 29 October 2026, actual drain and return workflows completed on Debian 13.7 /
Pacemaker 3.0.0 and Rocky Linux 9.8 / Pacemaker 2.1.10. The author's self-approval
returned HTTP 403 and an unapproved drain HTTP 409. A separate authenticated
editor approved the drain; the worker set standby, observed no active resources
on the selected member and retained quorum. Return review cleared approval; a
second independent approval allowed resume. Both plans completed with all members
online and outside standby, and the readiness page recorded the observed result.
The capacity statement described disposable lab workloads, not production load.
An additional independently approved drain preceded actual reboots of the second
Debian and Rocky members. Fresh guest boot times were verified, followed by new
return reviews, separate approvals and completed returns. NGINX and HAProxy
autostart were observed on both rebooted members.

A separate native Keepalived pair (Debian 13.7 and Rocky Linux 9.8) used only an
isolated RFC5737 network and test VIP. Its author could not self-approve or drain
without approval. The approved drain moved the VIP to the other member; TLS
trust, hostname, certificate fingerprint and HTTP 200 were verified through the
VIP. A newly reviewed, independently approved return completed with both services
active and exactly one VIP owner. HA readiness recorded the observed result.
These planned handovers do not qualify network partitions, physical fencing,
uninterrupted existing connections or production workload capacity.

The external entitlement adapter was used only to test PRs #443–#452. Login,
roles, independent approvals, SSH and actual cluster operations remained real;
the real subscription service was not qualified.

Offline simulation follows the official
[Pacemaker scheduler tool](https://github.com/ClusterLabs/pacemaker/blob/main/tools/crm_simulate.c).

## Review follow-up verification

New regressions reproduce a failed standby after approval, IPv4-mapped IPv6
sessions, real API deletion/update during a reservation, preserved boot policies,
interrupted holds/restores and reused registration IDs. Readiness uses the
registration-aware evidence key, including observed drain/return proof.

The native startup-policy helper is separately qualified with disposable systemd
units on Debian and Rocky Linux labs. Debian ran both cases through pytest;
Rocky Linux ran the same test function for enabled/disabled policies using its
standard Python runtime, with SELinux enforcing. These checks cover persistent
masking, rejected activation while masked, and restoration of the original
policy. They never touch the real Keepalived unit and do not reboot either VM. The older
full Debian/Rocky drain/reboot qualification above predates this follow-up and
is not a new live claim for the rewritten commit.

## Upgrading installations with existing plans

Finish or recover every active legacy maintenance plan through its independently
approved return before upgrading. Plans without a verifiable registration identity
cannot safely be rebound just because the numeric cluster ID matches. The identity
migration rejects such busy legacy plans before changing its schema; a separate
maintenance migration also checks installations where the readiness migration was
already applied. It rejects undecryptable or mismatched busy plans with a recovery
message, while allowing completed legacy history and current identity-bound work.
Do not clear a reservation just to bypass this check; establish the host's state
and complete the reviewed return using the previous application version first.
