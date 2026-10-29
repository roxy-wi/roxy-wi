# Container versions in Admin area → Update

The update page uses active worker heartbeats for Checker, Metrics, Port Scanner
and Socket. It compares complete versions, including multiple active versions,
instead of converting version strings to floating-point numbers. Database
bootstrap values are not evidence that a container service is installed.

Docker, Podman and Kubernetes installations show external update guidance rather
than local RPM/DEB installation actions. This page does not replace images or
control an engine. Package deployments retain local package update actions;
a remote worker does not enable an update of a missing local package.

## Optional deployment inventory

Auto Start and Prometheus exporter do not send the distributed-worker
heartbeats. To show them, or installed but stopped containers, run
`docker/collect_service_inventory.py` on the deployment host as the engine owner.
The collector calls only container listing, container/image inspection, and
optionally local package queries. It does not start, stop, enter or replace
containers, and never publishes environment variables or full inspect output.
The Web container does not need an engine socket or host-engine privileges.

Example for a rootful Podman deployment with application GID 10001 and named
volume `roxywi-data`:

```sh
sudo install -m 0755 docker/collect_service_inventory.py /usr/local/sbin/roxywi-service-inventory
sudo podman volume inspect roxywi-data --format '{{.Mountpoint}}'
```

Use the reported mount point, not a guessed storage path:

```sh
sudo /usr/local/sbin/roxywi-service-inventory --engine podman --gid 10001 \
  --output /ACTUAL/VOLUME/MOUNTPOINT/runtime/deployment-inventory.json
```

The output path must be absolute and use real directories. The publisher refuses
symlinked parent directories and pins directory descriptors while replacing its
snapshot, so application-owned storage cannot redirect a privileged write. If
the engine's storage root uses an administrator-managed symlink, resolve that
root with `realpath` first and configure the resulting canonical path.

For Docker use `--engine docker` and Docker's actual volume mount point. The
application reads the snapshot inside its existing volume at
`/var/lib/roxy-wi/runtime/deployment-inventory.json`. Override this with
`ROXYWI_DEPLOYMENT_INVENTORY_FILE` or `[main] deployment_inventory_file` if needed.
`--packages` additionally inspects known Roxy-WI packages and their systemd
status on the collector host; it does not inspect packages inside containers.

Refresh the snapshot every 30 seconds using the deployment's existing service
manager. A rootful systemd example is:

```ini
# /etc/systemd/system/roxywi-service-inventory.service
[Unit]
Description=Read-only Roxy-WI deployment inventory

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/roxywi-service-inventory --engine podman --gid 10001 --output /ACTUAL/VOLUME/MOUNTPOINT/runtime/deployment-inventory.json

# /etc/systemd/system/roxywi-service-inventory.timer
[Unit]
Description=Refresh Roxy-WI deployment inventory

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
Unit=roxywi-service-inventory.service

[Install]
WantedBy=timers.target
```

After reviewing the actual engine, volume path and permissions, reload systemd
and enable the timer. Do not install these example units unchanged. For rootless
engines, use the owning user and verify the mapped output ownership separately;
rootless deployment qualification is outside this change.

## Evidence and limits

- The collector recognizes standard Roxy-WI names and Compose service labels in
  Roxy-WI projects or official Roxy-WI images. Unrelated containers are ignored.
  Give custom deployments the corresponding standard names or Compose labels.
- Versions come from the immutable deployed image's OCI version label, or a
  numeric pinned tag. An unversioned image such as `latest` without a version
  label is reported with an unknown version. An image version identifies the
  deployed artifact; it is not a binary execution probe.
- Active worker version reports take precedence over image metadata. Local
  inventory can confirm an installed container even when it is stopped.
- An absent local record means **not detected on the inventory host**, not
  globally uninstalled: remote workers may be deployed elsewhere.
- Snapshots expire after 120 seconds. Missing, malformed, incomplete, oversized
  or future-dated snapshots are ignored. Engine failures leave the previous
  snapshot untouched, so its evidence expires rather than becoming an empty,
  apparently successful inventory.
- Existing credentials, images, mounts, worker identities and database records
  are not changed by version collection or page rendering.

Run the focused regressions with:

```sh
python -m pytest tests/unit/admin/test_update_overview.py tests/unit/admin/test_admin_tools.py \
  tests/unit/admin/test_admin_action_menus.py tests/smoke/test_version_updates.py -q
```

On an isolated Linux engine host, qualify real image metadata, running/stopped
state and secret exclusion with the host's system Python (3.9 or later):

```sh
ROXYWI_TEST_CONTAINER_INVENTORY=1 ROXYWI_TEST_INVENTORY_ENGINE=podman \
  python3 tests/integration/test_update_inventory_engine_linux.py -v
```

Use `docker` for Docker. The test owns uniquely named fixtures and removes only
those fixtures; it does not change existing containers. The Linux CI job runs
the Docker qualification automatically. See the [screenshot qualification
notes](screenshots/update-overview/README.md) for live UI evidence and its limits.
