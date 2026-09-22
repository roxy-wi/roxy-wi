# Let's Encrypt

> Applies to **Roxy-WI 9.1 and later**.

Certificate issuance, renewal and HAProxy deployment use Scheduler, Operations
and RabbitMQ in both package and Compose installations. The SSL page shows the
expiry date, next check/retry, target deployment status and recent operations.
New certificates created in the UI start as drafts: **Save draft → Check setup
(staging) → Issue certificate**. The setup check verifies DNS/CAA, SSH access,
the certificate directory, HAProxy configuration and Runtime API, then performs
a real staging challenge. Results are stored per domain and server. Production
issuance requires a successful check of the current configuration and DNS profile
within the last 24 hours. Editing a draft or rotating its profile requires a new
check. Drafts are never issued automatically. API clients retain direct issuance
by default; send `draft: true` to use this workflow and PATCH `action: preflight`
followed by `action: issue` after checking the result.

For active certificates the menu supports editing, a renewal check, a staging
test and retry. Checks run every 12 hours; Certbot decides whether renewal is due
using ARI and its native lifetime rules. Imported PEMs consult ARI with a
lifetime-based fallback until a managed Certbot lineage has been created.
Failed operations normally retry after 5 and 10 minutes. ACME rate limits retain
their `Retry-After` deadline and block early production retries, including edits.
Diagnostics classify CAA, DNS credentials, DNS propagation and HTTP validation
failures without exposing provider responses or secrets.

DNS challenges support Cloudflare, DigitalOcean, Linode and Route53. Certbot and
its plugins are installed from `requirements.txt` when building the image or
updating the package environment. The Operations process needs no sudo, package
manager or cron for DNS issuance. DNS tokens are encrypted with `secret_phrase`,
excluded from API responses and supported by `rotate_credential_secret.py`.
Omitting a token (or sending null) on PUT preserves it for the same provider.
The **DNS profiles** dialog manages reusable credentials within the current
group. Select a profile when creating/editing a certificate; token rotation is
used by subsequent operations without copying secrets into each certificate.
Profiles in use cannot be deleted. Propagation delay is configurable for
Cloudflare, DigitalOcean and Linode; Route53 uses the plugin's native polling.
The API is `/service/letsencrypt/dns-profiles` (GET/POST) and
`/service/letsencrypt/dns-profiles/<id>` (PUT/DELETE).

Standalone issuance runs Certbot once on the selected server, then delivers the
certificate to that server and its HA children in the same group. The managed
server needs Python 3, SSH and noninteractive sudo (or root SSH); Certbot is
installed through apt/dnf/yum if missing. Enable EPEL first where required.
Public port 80 must route `/.well-known/acme-challenge/` to port 8888 on the
selected server. Wildcards require a DNS provider. A staging test makes a real
ACME challenge but does not replace or deploy a production certificate.

Private ACME state and worker locks live in `lib_path/letsencrypt`; preserve this
directory, the database and `secret_phrase` across container recreation. All
Operations replicas must share the same filesystem and key. DNS issuance reuses
an ACME account per group and CA; standalone issuance reuses one per group, CA and
issuer host. Existing lineages keep their account identity. The managed
standalone server stores isolated Certbot state under
`/var/lib/roxy-wi/letsencrypt`. Certificate/key matching, exact SANs and validity
are checked before deployment. PEM replacement is atomic, with persistent
rollback state, HAProxy configuration validation and reload. Deployment verifies
a new HAProxy worker through `haproxy_sock_port` and checks the loaded certificate
fingerprint. A certificate deliberately not referenced by a bind is reported as
stored but unused. The Runtime API must be reachable from the managed host.
Docker HAProxy uses
its configured container name, a persistent directory mount for `cert_path`,
and the master-worker USR2 reload signal (HAProxy PID 1 with `-W` or `-Ws`). Host
configuration paths are mapped through the container mounts. Individual certificate file mounts
are not supported for atomic replacement. The PEM filename stays stable when
editing domains; the UI displays that filename.

If any HA target fails, all attempted targets are rolled back immediately. Remote
backups remain until all targets succeed and the applied configuration is saved.
Interrupted rollback/finalization is persisted and retried before new issuance;
editing and deletion remain blocked while recovery is pending. After three failed
replacement attempts and successful rollback, renewal of the previous applied
configuration resumes. Edit to submit another replacement. Certificate selection
and configuration preview remain available on the existing Add pages.

Scheduler checks expiry and recovery alerts every five minutes. Alerts fire at
14, 7, 3 and 1 days before expiry, at expiry, after repeated failures or failed
rollback, and upon recovery. They use the existing HAProxy alert routing for the
server and the durable notification outbox, with deduplication. Delivered and
cancelled LE notifications are retained for 30 days.

DELETE stops renewal and removes managed ACME material after successful cleanup.
It retains deployed PEMs so existing HAProxy configurations continue to work;
it does not revoke the certificate. Failed cleanup stays visible and retryable.
Completed/failed Operations history is retained for 30 days, except the last
and active operations. `ROXYWI_LE_HISTORY_RETENTION_DAYS=0` disables pruning.

## Importing certificate jobs from cron

For certificates managed through cron, database migration encrypts stored
tokens and pauses their schedules until import completes. It does not start
duplicate renewals.

1. On the original package host, apply database migrations and finish LE
   setup operations. Stop web, Scheduler and Operations while cutting over.
2. Temporarily stop cron/crond and Certbot timers on that host and on standalone certificate hosts.
   Wait for any running Certbot or certificate rsync commands to finish.
3. As root on the original Roxy-WI host, run:

   ```sh
   /path/to/roxy-wi-python roxy_wi.py migrate-le-cron
   ```

   The command imports existing certificate/key pairs without issuing new
   certificates, removes only Roxy-WI LE cron entries, and archives the selected
   cron-managed renewal configurations so certbot.timer cannot renew them in parallel.
   Original live/archive certificate files remain in place. Root-only backups
   of crontabs and renewal configurations are kept in
   `/var/backups/roxy-wi-letsencrypt` on each affected host. Other cron entries and
   other Certbot lineages remain untouched. Failed cutover can be rerun; schedules
   are activated only after all hosts complete it. Inspect domain/key mismatches
   or duplicate PEM owners before retrying.
4. Restart cron and the stopped Certbot timers on the affected hosts. Keep Roxy-WI processes on the source host stopped when
   moving to Compose. Transfer `lib_path/letsencrypt` with the shared volume and
   ensure it is owned by the Operations user (UID/GID 10001 in the default image).
   For packages, migration uses the owner of `lib_path`; check that it matches
   the service user. Start web, Scheduler and Operations on the destination.

The first run verifies and deploys imported material, obtaining a replacement
when needed. Do not run this cutover inside a container: the original cron and
ACME state would not be visible.

## Release verification

The Tests workflow includes `le-linux-deployment`, which uses real SSH, Docker
HAProxy and TLS connections to verify reload, rollback, repeated finalization and
invalid PEM rejection. To run it on a disposable Linux test host with Docker,
OpenSSH server, OpenSSL and passwordless sudo, use
`ROXYWI_TEST_DOCKER_LE=1 python -m pytest tests/integration/test_letsencrypt_linux.py -q`.
It starts a temporary SSH daemon on loopback and a temporary HAProxy container;
do not run it against a production host. This test uses local certificates.
Before release, run **Check setup (staging)** with an owned public domain for
each deployed challenge type, including HTTP routing for standalone issuance.

[Documentation index](README.md) · [Project overview](../README.md)
