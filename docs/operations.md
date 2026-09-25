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

## View logs and follow new entries

Open **Admin area → Internal logs**, select **Roxy-WI · all processes** and choose a
time range. **Live** appends new records about every two seconds;
**Pause** keeps the position so Live can resume. Auto-scroll can be switched off
while inspecting earlier entries. Hiding the browser tab pauses Live. The browser
keeps at most 1000 rows and expires records outside the moving relative interval.

Both internal and service log pages offer relative presets (5 minutes through
7 days) and an absolute calendar range, including dates across midnight. Choose
browser time or UTC; that zone also applies to service records without an explicit
offset. Roxy-WI JSON records use UTC. Search and Exclude match literal text.
Internal logs only lists Roxy-WI sources; use its source selector to filter Web,
Scheduler, Operations or Service events. Open each service's Logs page from its
menu to view HAProxy, NGINX, Apache or Keepalived logs. The service is fixed by
the page; select a managed server and its log file. **Live** is also available
on these pages and for WAF logs, using the existing SSH credentials. It requires
Python 3 and noninteractive `sudo` access to run the read-only log helper on the
log host (the configured syslog server when central syslog is enabled). The helper
is sent over SSH and exits after each bounded read; no agent is installed.
Refresh and absolute time ranges continue to use ordinary SSH snapshots.

Service Live starts with a tail of the selected file, then reads from its byte
position. Signed cursors bind the position to the user, group, server, file and
filters; they work across web replicas sharing the application secret. Cursors
expire after 24 hours; Refresh starts a new view. Pause retains the cursor, and
temporary SSH failures retry with backoff up to 30 seconds. Permissions and
credentials are checked again on each request. No SSH session is kept while idle.

The reader waits for incomplete lines, detects truncation and follows renamed
files before reading their replacements. It also checks recent uncompressed
rotations for unread records and late writes. New HAProxy installations use
`delaycompress` so the most recent rotation remains readable. If a file has
already been deleted or compressed, the viewer reports a possible gap; Live is
not a durable log archive. Keep sufficient uncompressed retention to resume after
long pauses. Changing the source or filters starts a new view.

From Roxy-WI 9.1, fresh HAProxy and NGINX installations use JSON traffic logs by
default, including installations managed through Docker. Existing service
configuration files are preserved. NGINX keeps the `main` access-log format name,
so virtual hosts generated by Add use JSON too. Each line contains a timestamp,
severity, process, readable message and request/connection fields; JSON escaping
protects quotes and backslashes in request data. Optional NGINX upstream values
are strings because they can be absent or contain multiple results.

HAProxy sends logs to local rsyslog, which writes JSON to `access.log`,
`error.log` and `status.log` without a syslog prefix. HTTP and TCP frontends share
the format. Plain-text daemon messages and existing custom text formats are
wrapped in JSON by rsyslog. NGINX access logs use JSON, while error logs retain
the standard text format: native JSON error logging requires
[NGINX's commercial subscription](https://nginx.org/en/docs/ngx_core_module.html#error_log).

Structured records show time, severity, process and message. Expand a row for its
fields or the original record. Plain-text records remain readable as text. Find
highlights literal, case-sensitive matches in messages and details; press Enter
or Refresh to apply the query. Rows, Exclude and Auto-scroll are in Additional
filters. Opening a record keeps the scroll position while Live continues to
receive entries.

The **Overview** page uses the same journal and structured record viewer. Its
compact block shows the latest 10 matching entries from the past seven days,
newest first, with three initially visible. Expand the list to see the rest;
Find and Refresh search the journal, and the block title opens Internal logs.
When the journal is disabled, Overview reads the configured `roxy-wi.log` file.

The container journal is enabled by default alongside JSON stdout. It lives in
`lib_path/logs` on the existing shared volume, with separate files for each process,
5 MiB segments and seven-day retention. Expired segments are removed hourly when
records are written. All roles and web replicas must share that volume and UID.
Set `ROXYWI_LOG_STORE_ENABLED=0` to disable the journal, or
`ROXYWI_LOG_STORE_PATH` to use another shared writable directory. Package installs
continue to read their configured log directory; the journal is opt-in there.
Docker/Gunicorn access and error output remain available through container logs.
Fail2Ban and local Apache log choices are available only in package installations.

Group administrators see only structured entries tagged with their group ID.
Unattributed system/background entries are visible only to the super administrator
in the Default group. Live rechecks authentication and permissions on every poll.

Queries are bounded: up to 4 MiB per initial request, 128 local files, 256 KiB per
local file and 1000 returned rows, over a maximum 31-day interval. Service Live
reads up to 256 KiB per follow request, tracks up to 16 files and scans at most
4096 directory entries. Its initial tail retains at most 10,000 complete records;
individual records longer than 64 KiB are skipped with a notice. Backlogs drain
in bounded batches without consuming rows beyond the response limit. The UI reports when
older content is outside the snapshot, a file was truncated, or timestamps could
not be parsed. Common JSON, syslog, Apache and NGINX timestamps are supported;
yearless syslog dates use the year nearest the query end. Custom formats and
continuation lines without timestamps are excluded with a notice. Use the original
files or container logs for a complete export or older records outside these limits.

## Change Center tasks

Change Center stores queued commands in the database and sends them to Operations
through RabbitMQ. Web returns HTTP `202` with the change data and `tasks_ids` for
validation, deploy, rollback, resume, promotion, per-node retry/rollback/include
and drift requests. The change's `operation` field contains the task ID, status,
active flag and any failure message. Approval, scheduling, cancellation and pause
signals return their immediate result.

Use the change details and timeline to follow task progress. If a task stays queued,
check Scheduler, RabbitMQ and Operations. All application roles must share the
database, credential encryption key, saved configurations and `lib_path`.
Operations uses `lib_path/change-locks` to prevent overlapping execution of a
recovered task; this storage must support advisory file locks across workers.

An interrupted worker is detected after `ROXYWI_OPERATIONS_LEASE_SECONDS`
(default 300 seconds). Commands that had started require inspection of the remote
state before retry, resume or rollback. A Web restart does not interrupt queued
work. Pause is a signal to the active rollout and takes effect after the current
batch; cancelling a pending pause does not launch another worker.

Scheduler prunes completed Change Center task records older than 30 days every
hour, preserving active tasks and the latest task for each change. Set
`ROXYWI_CHANGE_HISTORY_RETENTION_DAYS` to change this period; `0` disables pruning.
This does not delete the change, configuration snapshots or its audit timeline.

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
