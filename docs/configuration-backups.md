# Configuration backups

> Applies to **Roxy-WI 9.1 and later**.

Filesystem and S3 backups use the dedicated Scheduler and Operations processes.
Both must be running, with RabbitMQ available. Git backup jobs use their own scheduling.
Schedules and run results survive process restarts in the database. Hourly jobs
run at the hour, daily jobs at midnight, weekly jobs on Sunday, and monthly jobs
on the first day. The host timezone is saved with each schedule; set
`ROXYWI_BACKUP_TIMEZONE` (an IANA timezone such as `Europe/Moscow`) before creating
or migrating schedules to override it. Timestamps returned by the API are UTC.
After downtime only one missed run is queued. Failed runs receive two retries,
after 60 and 120 seconds; each attempt appears in Operations. After the third
failure, the next regular schedule is used. Editing/deleting a queued or running
backup returns a conflict until it finishes.

Scheduler cleans up completed/failed backup Operations history every hour,
including completed schedule changes. History is retained for 30 days after
completion by default. Set `ROXYWI_BACKUP_HISTORY_RETENTION_DAYS` on Scheduler
to a non-negative number of days; `0` disables cleanup. Queued/running operations,
the active task and the last task of each schedule are always preserved,
including while a retry is pending. Each pass deletes at most 10,000 records in
batches of 500; any remaining backlog is handled on subsequent passes. Delayed
queue messages for removed operations are acknowledged without executing them.
This cleanup applies only to database history of native filesystem/S3 backups;
saved configuration files, remote backups and other Operations history are kept.

Workers copy the **saved configuration versions** from the configured
`[configs] *_save_configs_dir` directories; they do not fetch fresh configurations
from managed servers. Missing source files are reported as a failed operation.
In HA deployments all Operations workers must mount the same configuration
directories and `lib_path` on storage supporting shared advisory file locks.
The `lib_path/backup-locks` directory prevents overlapping transfers even after
a worker lease expires. Do not remove these lock files while workers are running.

Filesystem backups use SFTP on port 22 with the selected SSH credentials and
require a writable destination and the OpenSSH `posix-rename` extension. The
destination layout remains `RPATH/roxy-wi-configs-backup/configs/SERVICE_DIR`.
`backup` preserves remote versions removed locally. `synchronization` removes
only matching configuration files for that server after uploading the current
files; other servers and unrelated files remain intact. Files are staged and
replaced atomically, so an interrupted transfer does not truncate a destination.

S3 uses `boto3`, installed from `requirements.txt` when building the container or
installing/updating the package environment. No packages are installed during a
backup. The existing endpoint, bucket and access keys are used; a bare endpoint
defaults to HTTPS. `ROXYWI_BACKUP_S3_REGION` defaults to `us-east-1`. The existing
`HOSTNAME/SERVICE_DIR/FILENAME` object layout is preserved, remote objects are
never deleted, and unchanged objects written by this handler are skipped using
SHA-256 metadata. Credentials need bucket/object read and upload permissions;
bucket creation permission is needed only if the configured bucket is missing.
SDK requests have bounded connection/read timeouts and standard retries.
See the [Boto3 transfer documentation](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/upload_file.html).

## Importing cron backup schedules

For jobs imported from cron, Scheduler waits until the source host's root
crontab has been cleaned. This procedure applies only when cron backup jobs
exist. Run it on the **source package host**, using Roxy-WI 9.1 or later and
that installation's database:

1. Finish any queued/running backup setup operations. Stop the web,
   Scheduler and Operations services. Stop the cron daemon temporarily and wait
   for running backup transfers to finish. Do not edit crontab during cutover.
2. Install the updated Python requirements and run the following commands using
   that environment, preserving the original configuration and encryption key:

   ```shell
   python3 roxy_wi.py migrate
   sudo /path/to/roxy-wi-python roxy_wi.py migrate-backup-cron
   ```

3. The command saves a mode-0600 crontab copy under
   `lib_path/backup-cron-migration`, removes only Ansible-tagged Roxy-WI filesystem
   and S3 backup entries, verifies removal, then activates the schedules. User
   cron jobs, Git backups and certificate renewal jobs are preserved. The command
   can be repeated after an interrupted cutover. Run it on every former cron host
   before starting Scheduler if several hosts used the same database.
4. Restart cron. For a container migration, now move the database and shared
   configuration storage, keep Roxy-WI processes on the source host stopped, and start
   Scheduler and Operations on the destination. A catch-up backup is queued once.

Do not run the cutover inside a container: it cannot inspect the original host's
crontab. Keep the saved crontab private because S3 cron commands contain keys.
The backup page and GET backup APIs show whether migration is required, the
next run/retry and the last operation status. Existing API response fields and
the `202`/`tasks_ids` contract for configuration changes are retained.

[Documentation index](README.md) · [Project overview](../README.md)
