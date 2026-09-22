# Release notes

These notes cover **Roxy-WI 9.1 and later**.

## 9.1.0

### Deployment and operations

- Run Web, Scheduler, Service Events and Operations as separate processes with
  durable background work through RabbitMQ.
- Deploy with Docker Compose or Helm, with explicit database migrations,
  persistent application storage and health probes for each role.
- Try the application locally with the HTTPS [Compose quick start](docs/quick-start.md).

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

- Follow a [Change Center tour](docs/change-center-tour.md), choose a deployment
  model and find restart, update, backup and certificate procedures in the
  [documentation index](docs/README.md).
- Use issue forms and contribution guidance to submit reproducible reports.

Before deploying, review [deployment](docs/deployment.md),
[operations](docs/operations.md) and your required [feature availability](docs/plans.md).
