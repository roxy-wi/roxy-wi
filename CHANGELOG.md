# Release notes

These notes cover **Roxy-WI 9.1 and later**.

## Unreleased

- Keep HA readiness history readable across key rotation, bind evidence to cluster
  registration lifetimes and stable server IDs, treat referenced fencing metadata
  conservatively, and preserve unsaved failure-domain edits during polling.
- Add durable request-path diagnostics for HAProxy/NGINX/Apache with discovered
  routing candidates, context-aware includes, pinned DNS/address probes,
  TCP/TLS-SNI/HTTP evidence, candidate-backend checks and group-scoped history.

- Add reviewed HA node maintenance with Change Center approval, offline Pacemaker
  placement/quorum checks, Keepalived VIP handover, observed drain/return,
  reservations, explicit recovery and configuration-bound maintenance evidence.

- Add a shared Keepalived/Pacemaker readiness page with durable read-only audits,
  per-member witness TLS/votes, configuration hashes, static fencing coverage,
  declared failure domains and configuration-bound external test attestations.
  Distinguish observations/configuration from functional failover verification.

- Add a shared Docker/Podman connector for managed component installation,
  explicit rootful/rootless adoption, namespace-aware statistics/Runtime API,
  configuration transactions, certificate mounts and lifecycle controls.
  Add Podman standalone witness installation and reviewed native conversion,
  image refresh, trust migration and recovery. New Podman VM qualification is
  pending; the controller deployment is a separate feature.
- Add a separate Podman Quadlet deployment profile for the Roxy-WI controller,
  using native GPG-encrypted Podman secrets instead of plaintext secret files,
  with system/rootless units, persistent SQLite and secrets, local HTTPS,
  readiness checks and explicit upgrades. Debian/EL live VM qualification is
  pending; managed-component Podman installation is a separate feature.

- Reject full Corosync membership replacement during validation and before apply.
  Require the selected witness address, active TLS and a vote on every resulting
  member before marking a membership/witness change applied.

- Keep unexpected Pacemaker exception details out of API errors while retaining
  deliberate input guidance. Restrict HA technology navigation to the same HTTP(S)
  origin and add security regressions for both boundaries.

- Add reviewed Docker-to-native witness conversion, fixed-recipe image refresh,
  cross-host witness/CA migration with local client keys and GUI recovery, plus
  planned custom Corosync-to-managed transport maintenance and explicit resume.
- Integrate ClusterLabs HA Cluster Exporter into Installation/Monitoring, with
  fixed checksums, actual metrics and Prometheus target output. Add native daemon
  Auto Start policy controls and prevent independent proxy recovery from fighting
  Pacemaker-owned applications.

- Add reviewed native-to-Docker witness conversion with a preserved NSS/CA database, host recovery timer and web recovery/log controls; replace membership JSON entry with discovered node tables.

- Standalone quorum witness installer supports a managed Docker variant with persistent TLS identity and container-aware cluster certificate setup.

- Add Corosync/Pacemaker under Services with group-scoped cluster registration,
  detected apt/dnf provisioning, resource/fencing and constraint forms, lossless CIB
  editing, validation/simulation and versioned patch commits.
- Add node/resource controls, encrypted configuration history, reviewed CIB
  restoration, coordinated membership changes, TLS net qdevice setup, journals
  and opt-in health notifications through the existing Operations infrastructure.
- Include cluster snapshots in credential-key rotation. Keep uncertain remote
  writes visible and prevent automatic replay of interrupted cluster operations.

- Add HA technology selection between Keepalived/VRRP and Corosync/Pacemaker,
  verified adoption, a standalone qnetd installation path and two-node quorum
  warnings. Preserve imported transport settings and existing witness certificates.
- Add explicit optional TCP SYN protection for new cluster nodes, platform checks,
  container workload agent choices and correct bundle action targets. Document
  implemented profiles separately from live-tested platforms and Docker support.

- Use separate service pages and standard Installation tables; invalidate CIB review
  after editor changes. Initialize fresh RPM qnetd certificate databases, prepare
  the Corosync state directory before validation, and offer native Proxmox fence
  agent installation with a narrow, backed-up repair for its known EPEL path defect.

- Discover installed agents and host network facts; generate parameter/timeouts
  from native metadata, offer cluster resource/node choices, and install/update
  repository agent packages through reviewed, version-pinned Operations jobs.

## 9.1.0

### Deployment and operations

- Run Web, Scheduler, Service Events and Operations as separate processes with
  durable background work through RabbitMQ.
- Deploy with Docker Compose or Helm, with explicit database migrations,
  persistent application storage and health probes for each role.
- Try the application locally with the HTTPS [Compose quick start](https://roxy-wi.org/description/operations#quickstart).

### Configuration backups

- Schedule filesystem and S3 backups through Scheduler and inspect attempts,
  retries and results in Operations.
- Transfer configuration versions over SFTP or through the Boto3 S3 client.
- Choose preservation or synchronization for filesystem destinations, and
  automatically prune completed backup operation history.

### Let's Encrypt

- Save certificate drafts, verify setup with a staging challenge, and issue
  certificates with per-domain and per-target diagnostics.
- Reuse encrypted DNS profiles and retain ACME accounts and renewal state.
- Schedule renewals with bounded retries, rate-limit handling and expiry alerts.
- Deploy certificates atomically to HAProxy targets with validation, reload
  verification and persistent rollback/recovery state.

### Documentation

- Follow the [Change Center guide](https://roxy-wi.org/description/change-center), choose a deployment
  model and find restart, update, backup and certificate procedures in the
  [documentation index](https://roxy-wi.org/description).
- Use issue forms and contribution guidance to submit reproducible reports.

Before deploying, review [deployment](https://roxy-wi.org/description/operations),
[operations](https://roxy-wi.org/description/operations#runtime) and your required [feature availability](https://roxy-wi.org/pricing).
