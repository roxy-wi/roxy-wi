# External certificate sources

Open **Services → HAProxy → SSL certificates → External certificate sources**.
A source downloads a certificate and key from a provider and uses Roxy-WI's
existing durable certificate deployment, runtime update and rollback workflow.
The first provider is [CertWarden](https://www.certwarden.com/docs/using_certificates/api_calls/).
[Native UI example](screenshots/certificate-sources/README.md).

No provider client needs to be installed on the HAProxy nodes. Existing manual
certificate uploads and Let's Encrypt issuance remain available.

## One deployment engine for every source

Manual updates, external providers and Let's Encrypt share `certificate_deployment`
for durable multi-node apply, commit and rollback. Issuance through Certbot and
provider retrieval stay in their existing adapters, with their own database and
history boundaries. Existing ACME journals and transaction identifiers remain
readable: recovery retains original receipts without issuing a new certificate or
repeating completed steps. Cluster placement and identity checks wrap the shared
engine for Pacemaker targets. Scheduler enumeration is materialized before enqueue
transactions so a policy rejection does not invalidate an open SQLite cursor on
Python 3.10.

## Configure and synchronize

1. Add a source. Enter the HTTPS server URL (without `/certwarden`), certificate
   name, certificate API key and private-key API key. For a private issuing CA,
   paste its PEM trust chain. TLS verification cannot be disabled; redirects are
   refused and credentials are sent only in an HTTP header. Environment proxies
   are not used for provider requests.
2. Select a primary HAProxy server. By default, its existing Master/Slave targets
   are included. Optionally select a Pacemaker cluster: the primary must be a
   member, and all current members are targeted, including standby members.
   Synchronization uses an observed active member for Runtime discovery even if
   the source was configured against a passive member.
3. Set a PEM filename and the expected certificate domains. The key must match
   the certificate, its dates must be valid and its names must cover the expected
   domains. Roxy-WI does not issue, revoke or alter the provider's certificates.
4. To replace a loaded PEM, use its current name. If multiple loaded directories
   contain that name, enter the exact directory. For a new PEM, click **Discover
   certificate destinations** and select a loaded directory or crt-list. The
   worker checks the current destinations again before deployment.
5. Save and run **Check provider**. This validates retrieval and certificate
   contents without writing to managed hosts. Run **Synchronize** to deploy, or
   enable periodic synchronization (5–10,080 minutes; default six hours).

API keys are encrypted in the database and omitted from read responses. Empty
key inputs retain their existing values on edit. Removing a source stops its
schedule and leaves already deployed certificates in place. Sources reserve their
PEM on every target, including when disabled: another source or Let's Encrypt
schedule cannot own the same PEM on an overlapping target. Remove the previous
owner before deliberately switching managers. Manual administrator changes remain
possible and are detected at the next synchronization.

## Operations, failure and recovery

The normal scheduler queues due sources and the Operations worker downloads and
deploys them. Run these services as described in [CONTRIBUTING](../CONTRIBUTING.md).
Saving a configuration alone does not prove that a deployment worked. Source
status distinguishes a provider check from synchronization; per-target deployment
and rollback results are available in the primary server's certificate history.

Every operation rechecks current group ownership, service permissions, protected
servers, direct-deployment policy, membership and addresses. Source editing and
removal are blocked during operations. For Pacemaker targets the cluster operation
lease covers deployment and recovery. No Pacemaker resources or CIB are changed;
Active HAProxy instances must support the certificate Runtime workflow. A
passive instance is handled through validated file staging as described below. A source is not a certificate shared-storage or application-data
replication mechanism.

A provider/TLS/content error leaves working certificates untouched. A deployment
failure uses the existing remote transaction journals to roll back started
targets. An incomplete rollback or finalization exposes **Retry deployment
recovery**. This acquires the same cluster lease and retries the recorded recovery,
without downloading or applying a different certificate. An interrupted apply is
rolled back before a fresh synchronization is allowed. Do not delete remote
transaction journals to bypass recovery. If membership or addresses changed,
inspect the original operation and restore access to its recorded targets before
recovery. Completed rollback is still reported as a failed synchronization; a new
synchronization can then be requested.

Deployment children are source-owned Operations records. The generic publisher,
stale-job reaper and worker do not dispatch them independently. A live source
heartbeat renews both records. After a worker interruption the source exposes
recovery even if an older release already queued its child. **Retry deployment
recovery** reacquires the source's cluster lease and rolls an interrupted apply
back; it never resumes that apply as an independent deployment. Existing encrypted
child journals remain recognizable after upgrade. A parent identifier alone is
insufficient to execute a child without its lease-renewal callback.

If a server is removed or a Pacemaker cluster is unregistered, the source remains
visible with `binding_status: unavailable`; other sources still load normally.
Checks and synchronization are refused until a valid target is selected. Use
**Edit** to choose a replacement registered server/cluster or **Remove source** to
delete only the binding, leaving deployed certificates untouched. An unfinished
operation still blocks edits/removal: restore access to its original recorded
targets and complete source recovery first. Deleting a registration does not
discard transaction journals or override group/protected-server permissions.

Identical provider material is skipped only if every target still presents the
accepted fingerprint, the complete normalized PEM revision and disk/runtime
agreement. Passive members must have the exact staged PEM and pass offline
startup validation; a matching leaf alone does not skip a changed chain. Changed member
lists or stale queued configurations fail before download/deployment. This checks
HAProxy's configured runtime certificate; end-to-end client TLS checks are a
separate function. Network requests and response sizes are bounded, and provider
response bodies and keys are not included in public errors. Failures retry at the
configured interval; they do not fall back to unverified HTTP or another provider.

## Active and passive Pacemaker members

Before reading or writing a member, Roxy-WI binds its selected service to exactly
one static Pacemaker resource, records the CIB configuration digest and observes
resource placement through `crm_mon`. All members must be online and clean, the
cluster quorate, and the selected resource managed, unblocked and not failed.
At least one selected instance must be active. Ambiguous bindings and conditional
resource parameters are refused rather than guessed.

Active instances receive the normal Runtime transaction. On a proved passive
member, the worker checks that the selected service/container is stopped and that
startup sources reference the requested certificate, directory or crt-list. It
stages the PEM through the same private transaction journal, validates its key and
certificate, then runs the complete startup configuration through HAProxy's offline
`-c` check. It never starts, reloads or relocates the cluster resource.
Certificate history labels these outcomes separately: **Active: Runtime verified**
and **Passive: file staged and startup configuration validated**. The latter is
not evidence of a client TLS handshake; use the [served TLS monitor](served-tls.md)
and a separately planned failover test for that evidence.

Supported passive bindings are native `systemd:haproxy` units, static native
`ocf:…:haproxy` resources using `conffile`, rootful `ocf:heartbeat:docker` or
`ocf:heartbeat:podman` resources, and rootful static Podman Quadlet units managed
as systemd resources. OCI images must already be present on each member. Removed
passive containers are reconstructed for inspection from their static image,
command and directory binds; the resource container is not created. Syntax checks
use the immutable local image in a temporary container with no network,
read-only directory binds and a private environment file. All capabilities are
dropped except `DAC_READ_SEARCH`, needed to read existing configuration files
owned by the SSH account without changing their host permissions. Host files
are not relabeled. Dynamic commands, named/file volumes, unresolvable startup
sources, rootless passive resource bindings and advanced Quadlet overrides require
an explicit supported binding before synchronization; there is no silent fallback
to a different engine or a host installation.

A placement change during deployment fails the operation and enters recorded
recovery. Recovery observes current placement while requiring the original CIB,
host, SSH identity and runtime binding. Known old/candidate files can be restored
on a stopped member without Runtime API. A staged member that has become active
must expose the expected Runtime certificate before finalization. If removing a
newly activated file or crt-list entry would break its current startup binding,
recovery refuses the removal: use the existing cluster standby/maintenance GUI to
drain that member, then retry certificate recovery. Unknown external file/runtime
changes are never overwritten. A repeated finalization rechecks the recorded file,
receipt and active Runtime or passive offline validation after a lost reply.

The automated suite covers placement/quorum/binding rejection, active-primary
selection from a passive source, all-member rollback, unchanged material,
configuration drift and interrupted acknowledgements. Linux integration exercises
the exact framed helper and real HAProxy offline validation; OCI checks run in an
opt-in disposable Docker/Podman environment. This is separate from live Debian/EL
cluster and failover qualification.

## Permissions and deployment policy

Source administration requires an operator role (1–3) and HAProxy permission.
Pacemaker targets additionally require the cluster service permission. Protected
hosts still require the existing elevated role, and direct-deployment policy is
checked at save, enqueue and worker execution. A scheduled operation uses the
source owner's current permissions. When policy requires Change Center approval,
direct certificate synchronization is refused; it does not bypass that policy.

Back up the credential encryption key with the database. The existing
`rotate_credential_secret.py` utility also rotates source configurations and
operation payloads; follow its normal offline rotation procedure.

## HTTP API

All routes use the existing authenticated session/JWT, active group and CSRF
protection. No endpoint returns a private key or saved API keys.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/service/certificate-sources/choices` | Providers/settings schemas, eligible group servers and clusters |
| GET/POST | `/service/certificate-sources/api` | List/create sources |
| GET/PUT/DELETE | `/service/certificate-sources/api/<id>` | Read/update/remove a source |
| POST | `/service/certificate-sources/api/<id>/check` | Queue provider/content validation |
| POST | `/service/certificate-sources/api/<id>/sync` | Queue synchronization |
| POST | `/service/certificate-sources/api/<id>/recover` | Queue recorded deployment recovery |

An update requires the current `revision`. Configure `name`, `provider`,
`settings`, `server_id`, optional `cluster_id`, `pem_name`, `domains`, optional
`directory` or `{kind, path}` `destination`, `interval_minutes` and `enabled`.
The `certwarden` settings are `url`, `certificate`, `certificate_api_key`,
`private_key_api_key`, and optional `ca_pem`. Action responses contain `task_id`
and `status`; poll the source and certificate history for the terminal result.

## Adding a provider

Implement a settings model, `label`, `secret_fields` and `fetch(settings)` in
`app/modules/connectors/certificates.py`, then register the implementation in
`PROVIDERS`. `fetch` returns a combined PEM chain and unencrypted private key to
validation/deployment in the worker. It must enforce verified transport, bounded
requests and safe errors. The GUI builds settings fields from the provider schema;
secrets belong in `secret_fields`. Provider code does not write managed hosts.

## Automated verification

`tests/unit/certificates/test_external_certificate_source_logic.py` covers provider transport,
secret handling, ownership conflicts, membership changes, repeated deliveries,
drift, multi-target rollback, lease renewal and interrupted-operation recovery.
`tests/product/test_certificate_source_workflows.py` uses real HTTP routes, authentication,
CSRF, database and certificate runtime helpers. Chromium tests in
`tests/product/browser/test_certificate_sources_browser.py` cover the native form,
saved-key redaction, synchronization/removal and narrow-screen layout. Credential
rotation is covered in `tests/security/test_secret_rotation.py`.

Regression scenarios also run the real stale-task recovery/claim/dispatch path,
including parent/child heartbeat renewal, queued children from older releases,
group-specific container defaults without an HTTP request, and removal or rebinding
after server deletion/cluster unregistration. Browser checks preserve the master's
Pacemaker refresh/retry/layout tests and cover source retry, unchanged table
geometry while loading, mobile dark mode and orphaned-binding editing. The source
and HA forms reuse the same shared workspace controls and styles as Pacemaker.

The automated fixtures use controlled responses and synthetic managed hosts.

## Recorded live qualification — 29 October 2026

A real CertWarden 0.30.1 backend supplied independently generated lab certificates
over verified HTTPS. Authenticated source creation/check/synchronization ran on
Debian 13.7 / Podman 5.4.2 and Rocky Linux 9.8 / Podman 5.8.2 with SELinux enforcing.
Saved API keys were redacted. A real provider-side rotation changed disk and
HAProxy Runtime fingerprints on both hosts; a served-TLS check verified the new
certificate and consistent peers. This tested retrieval/deployment, not ACME
issuance or availability of the provider's web administration UI.

Both Debian/Pacemaker 3.0.0 and Rocky/Pacemaker 2.1.10 two-member clusters then
received a temporary static `systemd:roxywi-haproxy` resource through the normal
CIB draft, validation and application API. A source deliberately configured
against the passive primary successfully updated the actual active Runtime and
staged/validated the stopped member's file without starting it. A separately
requested cluster move made that member active; its real CA/name-verified TLS
handshake presented the provider fingerprint and the fixture returned HTTP 200.
Unchanged resynchronization after the move passed. Temporary sources/resources
were removed through reviewed cleanup and both original CIB digests were restored.
This did not test arbitrary resource agents, promotion behavior or proxy boot
ownership during a cluster reboot.

The combined lab entitlement adapter was external to the repository and used
exclusively to test PRs #443–#452. Login, role/group checks, SSH, cluster placement
and actual certificate operations remained real. Real subscription activation
was not qualified; the adapter is not included in any commit.
