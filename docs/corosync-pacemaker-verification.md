# Corosync/Pacemaker verification record

Qualification dates: 2026-10-27–28. These are implementation/lab results, not vendor
certification or a guarantee for untested distributions, agents or deployments.
Documentation is versioned in this repository; it is not automatically published
to the Roxy-WI documentation website.

## Automated verification

| Scope | Result |
| --- | --- |
| Full available regression on upstream master `0f97d795`, including image-tag, API/navigation and membership/witness corrections | 2,968 passed, 610 skipped; 3 deprecation warnings, 10m35s |
| Pacemaker suite after membership/witness corrections | 217 passed; 2 deprecation warnings, including 13 new membership/witness regression cases. |
| Current affected suite | 263 passed; 2 deprecation warnings. Pacemaker, SSH/credential configuration, secret rotation, installer security, durable operation queue and admin tools. |
| Opt-in HTTP workflow suite before the security follow-up | 5 passed in 4m39s, 2 deprecation warnings: exporter/all daemon policies, refreshed-image native round trip, native and Docker CA rotation, cross-host witness move/return, planned transport maintenance/resume. Actual Debian and Rocky clusters and Operations were used. |
| Live Debian integration tests | 3 passed: adoption preserves CIB/Corosync, bootstrap refuses an existing cluster, CIB validation/commit/conflict and unique Dummy cleanup |
| Live Rocky 9.8 integration tests | The same 3 tests passed against the actual EL cluster |
| Fresh final controller Docker image | Built again after the membership/witness corrections; official entrypoint, database migrations, readiness, HTTP login, corrected module and bundled exporter role verified. No laboratory directory or SSH private key in the image. |
| Earlier repository Docker image qualification | Image build, official entrypoint/migrations/readiness/login; 102 backend tests passed, 9 JS tests skipped because the image has no Node.js; 3 live Debian cluster tests passed from the container |

The full regression was rerun after the image-tag, API/navigation and
membership/witness corrections. The earlier live
round-trip additionally verified that a later conversion retains the refreshed image. The fresh controller image test
covers startup and packaging; the three live cluster tests run from a controller
container belong to the earlier qualification, not the fresh-image smoke test.
Skipped browser/product tests require their optional external environments and
must not be counted as passed. Node.js checks run in the native suite.

## Membership and witness regression qualification (2026-10-28)

The initial test run reproduced both reported defects against the preceding
source. The corrected code passed all 217 Pacemaker tests. Its 13 new cases cover
full replacement during validation and application of a previously validated
draft, changed membership after validation, a successful partial replacement,
zero votes/inactive TLS/wrong witness on each member, verification of a newly
added member, and waiting for a temporarily unavailable vote. The tests use an
isolated database and mocked SSH; failed witness verification leaves the change
unknown and prevents automatic replay.

Actual authenticated HTTP draft, queued validation and queued application also
passed on both Debian 13.7 with a Docker witness and Rocky 9.8 with a native
witness. Each smoke test reapplied only byte-identical Corosync configuration,
verified TLS votes on both members and preserved the CIB digest. The three live
preservation/transaction tests were rerun on each platform: 3 passed on Debian
and 3 on Rocky. Broken witness connectivity and full replacement were reproduced
with mocks, not injected into the live clusters in this follow-up. A fresh
controller image containing both corrections also passed the official startup
smoke test; this does not rerun the live cluster suite from inside that container.

## Real VM qualification

Both platforms exercised the actual cluster tooling over SSH, and mutating HTTP
workflows used JWT/CSRF plus RabbitMQ/Operations rather than mock responses.

| Platform | Stack and exercised behavior |
| --- | --- |
| Debian GNU/Linux 13.7 (trixie) | Corosync `3.1.9-2+deb13u1`, Pacemaker `3.0.0-2`, qdevice and Docker qnetd `3.0.3-2`: native bootstrap, VIP/Dummy, ordering/colocation, reviewed CIB transactions, runtime move/clear and standby/online, independent TLS witness, third-node add/remove, monitoring, adoption and a real Proxmox fencing restart with resource recovery |
| Rocky Linux 9.8 (Blue Onyx) | Corosync `3.1.10-1.el9_8.2.x86_64`, Pacemaker `2.1.10-3.el9_8.x86_64`, qdevice/qnetd `3.0.4-1.el9.x86_64`, SELinux enforcing: native bootstrap, persistent SYN settings, qnetd-only installation with no Pacemaker/Corosync daemon packages, repeated witness installation preserves CA, TLS qdevice vote, VIP/Dummy, ordering/colocation, all implemented runtime action types, journals, monitoring, adoption and real fencing/resource failover/rejoin |
| Clean additional Rocky 9.8 host | Actual bootstrap preparation with the optional Proxmox fencing package: native DNF transaction, automatic known-defect repair, backed-up original, valid agent metadata and Corosync syntax before service startup |

The Rocky packaging qualification found and fixed two RPM prerequisites in the
installer: qnetd needs explicit initialization/ownership of a new NSS database,
and Corosync needs its state directory before pre-start syntax validation.
The EPEL `fence-agents-pve-4.10.0-30.el9` library placeholder defect was reproduced
from the original package, repaired through the installer helper, and verified
idempotent on both cluster nodes and on the additional clean host. Working agents
are left unchanged. The automatic repair does not configure a fence device or
hypervisor permissions.

Installed agent parameter names differ: the EL 4.10 agent uses `node_name`, while
the Debian 4.16 agent uses `pve_node`. The lab fence definitions were reviewed for
their actual installed metadata. Agent-specific device setup remains an operator
responsibility. The limited lab fencing account could read/control only explicitly
authorized disposable VMs; its request for the protected VM was verified denied.
The protected VM remained running throughout qualification.

## Native agent and host discovery qualification

Read-only checks against both registered clusters verified actual installed agents,
metadata, repository candidates and node hostnames/interfaces. Debian returned
470 common agents and 80 agent packages; Rocky returned 330 common agents and
53 packages before the additional package installation. These counts describe the
lab package set, not a fixed product catalog.

A real authenticated HTTP/CSRF request queued installation of the reviewed
`fence-agents-ipmilan-4.10.0-110.el9_8.7` package through Operations on both Rocky
nodes. Exact installed versions were verified afterward, and rediscovery exposed
`stonith:fence_ipmilan`. The existing CIB digest stayed unchanged and the cluster
remained quorate. The resulting Rocky inventory contained 337 common agents.

## Browser verification

The live interface was checked for separate service views, retained cluster
selection, Installation table/button consistency, new/adopt/witness mode switching,
two-node warning, actual resource creation/removal drafts, validation/apply,
confirmation/cancel, invalidation after XML editing, journal loading, all-node
quorum diagnostics and loading existing membership/witness settings. Discovery
of an already registered cluster disables duplicate adoption. Shared Roxy-WI
widgets, layout classes and confirmation dialogs are used; no Pacemaker-specific
stylesheet is required.

The discovery-driven resource form was also exercised against Rocky: select the
installed Dummy agent, load native parameters/timings, create a draft, validate,
apply and observe the running resource. Removal used the current CIB selector,
then validation/application restored the original resources. IPaddr2 metadata
produced its required IP field, optional fields and native timeouts. New-cluster
registration read the actual hostname and global interface addresses from a
Debian host, offered a separate explicit custom-address option and detected
its existing active Corosync service. No new cluster was registered on that host.

## Standalone Docker witness qualification

The optional Docker witness was built and installed on the independent Debian 13
amd64 VM. Its actual container package was qnetd 3.0.3-2. Repeating installation
preserved both the CA fingerprint and image ID; attempting a native replacement
was refused. Web checkbox/confirmation queued a real Operations installation and
reported Docker mode, version and CA fingerprint after completion. Final HTTP
checks also verified both pre-existing native witnesses remained active and both
application clusters remained quorate. The image itself was checked to contain no
initialized NSS/CA database; its running health check was healthy.

An isolated Rocky 9.8 Corosync/qdevice client completed the public-CA/request/signing
exchange through the container-aware helper. Native diagnostics reported TLS
required, TLS active with a client certificate and an available qdevice vote.
Stopping the container removed that vote/quorum; starting it restored them.
The existing Debian and Rocky application clusters retained their witnesses.
The isolated Corosync test configuration was restored and its services stopped.

The affected Pacemaker and SSH/security suite passed 160 tests with 2 existing
deprecation warnings after these additions. The earlier complete regression suite
above predates the Docker witness addition. The Docker engine installation path
on a host without Docker and an EL Docker host, plus other architectures, were
not qualified by that earlier test. Later lifecycle/image-recovery qualification
is recorded below. See the [Docker witness guide](corosync-pacemaker-witness-docker.md).

## Remaining qualification limits

- EL 8, other EL 9 distributions/releases and Ubuntu profiles have implementation
  and package-selection tests but no live qualification here.
- Agent selection verifies installation/discovery on every registered node; it
  does not qualify the workload. Non-Proxmox fencing hardware, promotable application semantics,
  arbitrary OCF agents and Docker/Podman workloads need workload-specific tests.
- Container agent/bundle generation is tested; this lab did not run every real
  container workload, storage integration or fencing topology.
- Monitoring checks and outbox integration are tested; delivery through each
  customer's SMTP/chat/webhook channel and the complete Helm deployment were
  not qualified in this lab.
- Custom transport conversion, witness host moves and CA rotation now have explicit
  GUI workflows. The qualification below covers the concrete tested scenarios;
  arbitrary multi-ring networks and other witness/crypto configurations need their own qualification.
- Multi-node transport commit cannot be an atomic transaction over an unreliable
  network. Unknown outcomes require explicit inspection/reconciliation.

Before production deployment, qualify the actual distribution packages, network,
agent/device credentials, fencing outcome, backup/restore and notification channels.
Use the [control/recovery reference](corosync-pacemaker-controls.md) and
[platform matrix](ha-support.md) for the implemented behavior and prerequisites.

## Exporter, Auto Start and advanced workflow qualification

The following tests used the normal authenticated HTTP API with CSRF,
Operations and real disposable VMs. Reproducible opt-in workflow tests and their
prerequisites are in the [testing guide](corosync-pacemaker-testing.md).

| Workflow | Observed result |
| --- | --- |
| Exporter | ClusterLabs 1.4.3 installed through Operations/Ansible on Debian 13 and Rocky 9.8; controller scraped both Pacemaker and Corosync metrics. Repeated installation also passed on both OSes. 13 metric families and 57/55 samples respectively; CIB digests unchanged. Version, metrics and Prometheus target also checked in the browser. |
| Daemon Auto Start | All on-failure/no/package-default choices applied/read through HTTP on Debian and Rocky without CIB changes. An isolated additional Rocky host restarted Corosync after SIGKILL, but stayed stopped after intentional stop; original policies restored and the isolated VM shut down. |
| Native → Docker | Real controller/witness conversion retained the CA and every TLS vote. Separate independent host-timer test restored native qnetd and all client votes, exit status 0. |
| Image update / reverse conversion | Running Docker witness rebuilt/updated, converted to native and back to Docker with the attached Debian cluster. CA unchanged and all TLS votes verified after every step. |
| Interrupted image update | Candidate image was made active and verified, deliberately left uncommitted, then GUI recovery restored the exact previous image, NSS/CA and every TLS vote. |
| Host move / CA | Actual Docker CA rotation, witness 104 → 105 → 104, and native Rocky CA rotation succeeded. Every client retained its locally generated private key; all TLS votes were verified and CIB digests remained unchanged. |
| Interrupted CA change | Deliberate controller failure after native Rocky CA/client switchover left a durable journal. Authenticated GUI recovery restored the original CA and verified every TLS vote. |
| Managed transport | Rocky applications were quiesced, token timeout changed under planned daemon restart, quorum/TLS votes verified and nodes kept in standby. Explicit resume restored VIP and Dummy. |
| Interrupted transport | Deliberate failure after all candidate transport files were installed left daemons stopped and a durable pending identity. GUI recovery restored the original token/configuration, full quorum and witness votes while retaining standby. Separate confirmed resume restored VIP/Dummy. |
| Adopted/custom transport | A real custom Corosync logging option was installed/loaded on both test nodes; registration represented adoption. The reviewed migration explicitly replaced that custom configuration with managed knet, enabled managed membership and resumed VIP/Dummy successfully. |

Host-move recovery deliberately uses a fail-stop order; simultaneous independent
arbiter reactivation is not attempted after an unreachable target. Late-timer guards, partial rename recovery, unrelated-container refusal,
per-node policy rollback, transport fail-stop restoration, role/tenant restrictions
and stale review refusal also have automated regression coverage. Native TLS
rotation was exercised with Rocky SELinux enforcing. No test operated on the
protected unrelated VM.

The current full and affected suite results are recorded at the top of this guide.
The final controller Docker image was freshly built and its official startup path
verified after the production image-tag and API/navigation security corrections. Complete Helm deployment and
every third-party resource agent remain outside this qualification.

## CodeQL follow-up

The review identified two raw exception-message responses, an unchecked DOM-derived
HA navigation destination and a test-only `docker.io` membership assertion that
CodeQL interpreted as a URL substring check. The API now returns generic messages
for unexpected parsing/value/SSH failures; deliberate input errors use the existing
client-safe error type and retain their actionable messages. HA navigation parses
the destination and requires HTTP(S) with the current origin. Package assertions
use exact argument equality, not substring matching.

Seven new API regression cases cover exception-detail suppression and deliberate
public errors. A separate browser-script regression covers legitimate prefixed
routes, dangerous schemes, external origins, disabled options and missing fields.
The affected suite passed 242 tests. The corrected application also passed all
three live preservation/transaction tests on each of Debian and Rocky, refused
invalid confirmations/DTD-bearing XML through authenticated HTTP without changing
either CIB, and switched HA technologies in both directions in the live browser.

Before this follow-up, eight additional post-publication lab checks passed in
6m54s: production-source hashes, independent Docker image-update rollback,
interrupted native/Docker CA recovery, interrupted Debian/Rocky transport recovery
and real fencing/failover/rejoin on both platforms. An initial watchdog-test poll
collided with the recovery's exclusive lock; the host restored successfully.
Only the private test polling needed correction before the complete rerun passed.
These results apply to the earlier revision and are not a rerun of all failure
scenarios after the API/navigation-only security correction.
