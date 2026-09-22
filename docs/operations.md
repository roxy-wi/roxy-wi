# Operate Roxy-WI

> Applies to **Roxy-WI 9.1 and later**.

## Restart

For a Compose installation using the MariaDB manifest:

```sh
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml restart web scheduler service-events operations
```

This restarts the application roles with the installed image and configuration.
To apply source, image or environment changes, use the update procedure below.
Use the project name and manifest selected during your installation; the
[local quick start](quick-start.md) has its own launcher and project.

For packages, restart Web, Scheduler, Service Events and Operations through the
service manager configured by your installation. Keep exactly one Scheduler.
The [process role reference](deployment.md#process-roles) lists their entry points.

## Apply an update with Compose

Run from the repository root after placing the intended source revision there.
Allow active Operations to finish and take a consistent backup before migrating.

```sh
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml build
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml stop web scheduler service-events operations
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml run --rm migrate
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml up --detach --wait --wait-timeout 300
```

Proceed to the last command only if migration succeeds. Keep the application
stopped if it fails, inspect the migration output and resolve that failure first.
Do not regenerate secrets or reinitialize a database to fix a startup error.

Image changes need a rebuild and container recreation; environment changes need
container recreation. An ordinary restart does not apply either.

## Check health and diagnose failures

```sh
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml ps
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml logs --tail 100 web scheduler service-events operations
docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml exec -T operations python3 roxy_wi.py healthcheck --role operations --check ready
```

Web exposes `/health/live` and `/health/ready`. Background roles have their own
health probes; a ready Web process alone does not prove that scheduled jobs can
run. Use `scheduler`, `service-events` or `operations` with the probe above.

| Symptom | Check |
| --- | --- |
| Login does not persist | HTTPS, `ROXYWI_PUBLIC_URL`, proxy headers and browser cookies. Authentication cookies require HTTPS. |
| An operation stays queued | RabbitMQ connectivity and Operations readiness. |
| Scheduled work does not appear | Scheduler readiness, the saved timezone, next run/retry and schedule migration status. |
| Stored credentials cannot be decrypted | The configured `secret_phrase` must match the key used when credentials were stored. |
| A configuration backup fails | Saved configuration files, shared storage and destination permissions; see [backups](configuration-backups.md). |
| Certificate issuance or deployment fails | Per-domain and per-target diagnostics on the SSL page; see [LE](letsencrypt.md). |

## Preserve and restore application state

Configuration backups copy saved proxy configurations. They do **not** back up the
whole Roxy-WI installation. For disaster recovery, preserve:

- A consistent database backup, including Operations and schedule records.
- The entire configured `lib_path`, including saved configurations, private
  Let's Encrypt state and pending deployment recovery files.
- Configuration files, environment secrets and the credential encryption key.
- RabbitMQ state, or a documented recovery procedure for its durable queues.

Pause application writers before a filesystem snapshot. Use database-native
backup tools for MariaDB/MySQL. For SQLite, use its backup API or copy the database
with all writers stopped; a live copy of only the main database file can miss WAL
contents. Keep backups private and verify restoration on a separate installation.

Restore the matching database, files and keys together with their required
ownership. Start dependencies, apply the intended version's migrations and check
role readiness before admitting traffic. Inspect interrupted Operations and
certificate recovery on the restored instance before enabling scheduled work.

[Documentation index](README.md) · [Configuration](configuration.md)
