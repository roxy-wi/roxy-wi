# ![alt text](https://roxy-wi.org/static/images/logo_menu.png "Logo")
Web interface (user-friendly web GUI, alerting, monitoring, and secure) for managing HAProxy, Nginx, and Keepalived servers. Leave your [feedback](https://github.com/hap-wi/roxy-wi/issues)

# Get involved
* [Telegram Channel](https://t.me/roxy_wi_channel) about Roxy-WI, talks and questions are welcome

# Demo site
[Demo site](https://demo.roxy-wi.org) Login/password: admin/admin. Server resets every hour.

![alt text](https://roxy-wi.org/static/images/viewstat.png "HAProxy state page")

# Features:
1. Installing and updating HAProxy, Nginx, Apache and Keepalived with Roxy-WI as a system service
2. Installing and updating HAProxy and Nginx with Roxy-WI as a Docker service
3. Installing and updating HAProxy, Nginx, Apache, Keepalived, and Node exporters with Roxy-WI
4. Downloading, updating, and formatting GeoIP to the acceptable format for HAProxy, and NGINX with Roxy-WI
5. Dynamic change of Maxconn, Black/white lists, add, edit, or delete backend's IP address and port with saving changes to the config file
6. Configuring HAProxy, Nginx, Apache and Keepalived in a jiffy with Roxy-WI
7. Viewing and analyzing the status of all Frontend/backend servers via Roxy-WI from a single control panel
8. Enabling/disabling servers through stats page without rebooting HAProxy
9. Viewing/Analyzing HAProxy, Nginx, Apache and Keepalived logs right from the Roxy-WI web interface
10. Creating and visualizing the HAProxy workflow from Web Ui
11. Pushing Your changes to your HAProxy, Nginx, Apache, and Keepalived servers with a single click via the web interface
12. Getting info on past changes, evaluating your config files, and restoring the previous stable config at any time with a single click right from the Web interface
13. Adding/Editing Frontend or backend servers via the web interface with a click
14. Editing the config of HAProxy, Nginx, Apache, and Keepalived and push interchanges to All Master/Slave servers by a single click
15. Adding Multiple servers to ensure the Config Sync between servers
16. Managing the ports assigned to Frontend automatically
17. Evaluating the changes of recent configs pushed to HAProxy, Nginx, Apache, and Keepalived instances right from the Web UI
18. Multiple User Roles support for privileged-based Viewing and editing of Config
19. Creating Groups and adding/removing servers to ensure the proper identification for your HAProxy, Nginx, and Apache Clusters
20. Sending notifications from Roxy-WI via Telegram, Slack, Email, PageDuty, Mattermost, and via the web interface
21. Supporting high Availability to ensure uptime to all Master slave servers configured
22. Support of SSL (including Let's Encrypt)
23. Support of SSH Key for managing multiple HAProxy, Nginx, Apache, and Keepalived Servers straight from Roxy-WI
24. SYN flood protect
25. Alerting about changes of the state of HAProxy backends, about approaching the limit of Maxconn
26. Alerting about the state of HAProxy, Nginx, Apache, and Keepalived service
27. Gathering metrics for incoming connections
28. Web acceleration settings
29. Firewall for web application (WAF)
30. LDAP support
31. Keep active HAProxy, Nginx, Apache, and Keepalived services
32. Possibility to hide parts of the config with tags for users with the "guest" role: "HideBlockStart" and "HideBlockEnd"
33. Mobile-ready design
34. [SMON](https://roxy-wi.org/services/smon) (Check: Ping, TCP/UDP, HTTP(s), SSL expiry, HTTP body answer, DNS records, Status pages)
35. Backup HAProxy, Nginx, Apache, and Keepalived config files through Roxy-WI



![alt text](https://roxy-wi.org/static/images/roxy-wi-metrics.png "Merics")

# Install

## RPM

### Read instruction on the official [site](https://roxy-wi.org/installation#rpm)

## DEB

### Read instruction on the official [site](https://roxy-wi.org/installation#deb)

# OS support
Roxy-WI supports the following OSes:
1. EL7(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
2. EL8(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
3. EL9(RPM installation and manual installation). It must be "Infrastructure Server" at least. x86_64 only
4. Amazon Linux 2(RPM installation and manual installation). x86_64 only
5. Ubuntu (DEB installation and manual installation). x86_64 only
6. Other Linux distributions (manual installation only). x86_64 only

![alt text](https://roxy-wi.org/static/images/smon_dashboard.png "SMON area")

# Database support

Default Roxy-WI use Sqlite, if you want use MySQL enable in config, and create database:

### For MySQL support:

### Read instruction on the official [site](https://roxy-wi.org/installation#database)

![alt text](https://roxy-wi.org/static/images/roxy-wi-overview.webp "Overview page")

# Settings


Login at `https://roxy-wi-server/admin`, then add users, groups, and servers. Set the initial admin password with `ROXYWI_BOOTSTRAP_ADMIN_PASSWORD` (at least 12 characters). If it is not set, Roxy-WI creates `/var/lib/roxy-wi/bootstrap-admin-password` with mode `0600` on first start.

Fresh installations generate random HAProxy, NGINX, Apache statistics passwords. Set `ROXYWI_RABBITMQ_PASSWORD` (at least 12 characters) before the first start when RabbitMQ is configured separately; otherwise a random value is stored in the admin settings. Existing installations that still use the old `password` or `roxy-wi123` defaults must replace them in both Roxy-WI settings and the corresponding service.

Store a unique Fernet key as `[main] secret_phrase` in `/etc/roxy-wi/roxy-wi.cfg`. `ROXYWI_SECRET_PHRASE` is an optional override and, when non-empty, takes precedence over the config file. Existing installations must keep their current unique key; no credential rotation is required during a normal code upgrade. Rotate only when deliberately replacing a key: set the previous key as `ROXYWI_OLD_SECRET_PHRASE`, the replacement as `ROXYWI_SECRET_PHRASE`, and run `python3 rotate_credential_secret.py` once before restarting the application. Install the TLS certificate and private key as `/etc/roxy-wi/certs/roxy-wi.crt` and `/etc/roxy-wi/certs/roxy-wi.key`; the private key must not be stored below the web application root. SSH connections automatically accept previously unknown host keys; a changed key that conflicts with a known key is still rejected.

## Scheduler

The scheduler HTTP API is permanently disabled. Web workers do not start background jobs by default, which prevents the same job from running once per worker. Run exactly one dedicated scheduler process under your service manager:

```shell
python3 scheduler_runner.py
```

`scheduler_runner.py` enables `ROXYWI_SCHEDULER_ENABLED=1` for that process. Do not set this variable globally for the web service.

## Configuration backups

Filesystem and S3 backups use the dedicated Scheduler and Operations processes.
Both must be running, with RabbitMQ available. Git backup jobs are unchanged.
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

### Upgrading existing cron backups

Existing filesystem/S3 schedules remain paused in the new scheduler until the
original root crontab has been cleaned. New installations need no cutover.
On the **original package host**, using the new code and the original database:

1. Finish any queued/running legacy backup setup operations. Stop the web,
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
   configuration storage, keep the old Roxy-WI processes stopped, and start the
   new Scheduler and Operations services. A catch-up backup is queued once.

Do not run the cutover inside a container: it cannot inspect the original host's
crontab. Keep the saved crontab private because old S3 commands contain keys.
The backup page and GET backup APIs show whether migration is required, the
next run/retry and the last operation status. Existing API response fields and
the `202`/`tasks_ids` contract for configuration changes are retained.

## Let's Encrypt

Certificate issuance, renewal and HAProxy deployment use Scheduler, Operations
and RabbitMQ in both package and Compose installations. The SSL page shows the
expiry date, next check/retry, target deployment status and recent operations.
The action menu supports editing, a renewal check, a staging test and retry.
Checks run every 12 hours; failed operations retry after 5 and 10 minutes.
A failed replacement keeps the applied configuration; after three failures its
normal renewals resume. Edit the configuration to submit another replacement.

DNS challenges support Cloudflare, DigitalOcean, Linode and Route53. Certbot and
its plugins are installed from `requirements.txt` when building the image or
updating the package environment. The Operations process needs no sudo, package
manager or cron for DNS issuance. DNS tokens are encrypted with `secret_phrase`,
excluded from API responses and supported by `rotate_credential_secret.py`.
Omitting a token (or sending null) on PUT preserves it for the same provider.

Standalone issuance runs Certbot once on the selected server, then delivers the
certificate to that server and its HA children in the same group. The managed
server needs Python 3, SSH and noninteractive sudo (or root SSH); Certbot is
installed through apt/dnf/yum if missing. Enable EPEL first where required.
Public port 80 must route `/.well-known/acme-challenge/` to port 8888 on the
selected server. Wildcards require a DNS provider. A staging test makes a real
ACME challenge but does not replace or deploy a production certificate.

Private ACME state and worker locks live in `lib_path/letsencrypt`; preserve this
directory, the database and `secret_phrase` across container recreation. All
Operations replicas must share the same filesystem and key. The managed
standalone server stores isolated Certbot state under
`/var/lib/roxy-wi/letsencrypt`. Certificate/key matching, exact SANs and validity
are checked before deployment. PEM replacement is atomic, with persistent
rollback state, HAProxy configuration validation and reload. Docker HAProxy uses
its configured container name, a persistent directory mount for `cert_path`,
and the master-worker USR2 reload signal (HAProxy PID 1 with `-W` or `-Ws`). Host
configuration paths are mapped through the container mounts. Individual certificate file mounts
are not supported for atomic replacement. The PEM filename stays stable when
editing domains; the UI displays that filename.

DELETE stops renewal and removes managed ACME material after successful cleanup.
It retains deployed PEMs so existing HAProxy configurations continue to work;
it does not revoke the certificate. Failed cleanup stays visible and retryable.
Completed/failed Operations history is retained for 30 days, except the last
and active operations. `ROXYWI_LE_HISTORY_RETENTION_DAYS=0` disables pruning.

### Migrating existing LE jobs

Database migration encrypts existing tokens and marks old records as waiting
for migration. It does not start duplicate renewals.

1. On the original package host, apply database migrations and finish legacy LE
   setup operations. Stop web, Scheduler and Operations while cutting over.
2. Temporarily stop cron/crond and legacy Certbot timers on that host and on standalone certificate hosts.
   Wait for any running Certbot or certificate rsync commands to finish.
3. As root on the original Roxy-WI host, run:

   ```sh
   /path/to/roxy-wi-python roxy_wi.py migrate-le-cron
   ```

   The command imports existing certificate/key pairs without issuing new
   certificates, removes only Roxy-WI LE cron entries, and archives the selected
   legacy renewal configurations so certbot.timer cannot renew them in parallel.
   Original live/archive certificate files remain in place. Root-only backups
   of crontabs and renewal configurations are kept in
   `/var/backups/roxy-wi-letsencrypt` on each affected host. Other cron entries and
   other Certbot lineages remain untouched. Failed cutover can be rerun; schedules
   are activated only after all hosts complete it. Inspect domain/key mismatches
   or duplicate PEM owners before retrying.
4. Restart cron and the stopped Certbot timers on the affected hosts. Keep old Roxy-WI processes stopped when
   moving to Compose. Transfer `lib_path/letsencrypt` with the shared volume and
   ensure it is owned by the Operations user (UID/GID 10001 in the default image).
   For packages, migration uses the owner of `lib_path`; check that it matches
   the service user. Start the new web, Scheduler and Operations processes.

The first run verifies and deploys imported material, obtaining a replacement
when needed. Do not run this cutover inside a container: the original cron and
ACME state would not be visible.

## OpenID Connect

Super administrators can configure one or more OIDC providers under **Admin → OIDC**. Roxy-WI supports discovery metadata, signed ID token validation through JWKS, optional UserInfo claims, verified-email/domain policies, automatic user creation or email linking, and external-group mappings to Roxy-WI groups and roles. Local and LDAP login remain available.

When Roxy-WI is behind a reverse proxy, set `ROXYWI_PUBLIC_URL` to its canonical external origin, without a trailing slash, for example `https://roxy-wi.example.com`. Register the callback URL shown in the provider form at the identity provider. The usual scopes are `openid email profile`; add the provider-specific groups scope when group mapping is used.

OIDC client secrets are encrypted with the existing `[main] secret_phrase` Fernet key. Keep the same key during a normal upgrade; no new key or credential rotation is required.

### Read instruction on the official [site](https://roxy-wi.org/settings)

![alt text](https://roxy-wi.org/static/images/hapwi_overview.webp "HAProxy server overview page")


![alt text](https://roxy-wi.org/static/images/add.webp "Add proxy page")



# Troubleshooting
If you have error:
```
Internal Server Error
```

Do this:
```
$ cd /var/www/haproxy-wi/app
$ ./create_db.py
```

[Read more](https://roxy-wi.org/troubleshooting)
