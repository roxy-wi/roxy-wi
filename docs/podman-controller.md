# Roxy-WI controller on Podman Quadlet

This deploys **Roxy-WI itself**, including Web, Scheduler, Service Events,
Operations, RabbitMQ and a local HTTPS endpoint. Installing managed proxies
through the Roxy-WI GUI is a separate workflow. This profile uses native Quadlet
units, rather than a Docker compatibility socket or a Compose provider.

**Evaluation qualification:** automated tests validate generation, persistent
secrets, ownership checks and failure handling. Live rootful and rootless startup,
verified HTTPS, login, same-image upgrades, reboot and encrypted credential
retention passed on the Debian and Rocky Linux profiles recorded below. This
does not establish compatibility with a historical database schema or an
unrelated host's firewall, kernel, GPG or rootless-network setup.

## Requirements and scope

- Linux with systemd, cgroup v2, Python 3.10+ and Podman **4.9+** including Quadlet.
  Verify the installed version; distribution names alone do not establish
  compatibility. Rootless networking and subordinate UID/GID mappings must
  already work for a rootless deployment.
- The host init helper used by `podman run --init`. On Debian, install
  `catatonit` explicitly when recommended packages are disabled. Enterprise Linux
  Podman packages may supply their own helper. Start/upgrade probes the actual
  selected image with an isolated `/bin/true` process before creating controller
  state; `prepare` only generates configuration and does not run that probe.
- GnuPG and an encryption-capable GPG key available to the **same Podman owner**.
  Podman's `pass` secret driver must be able to encrypt and decrypt noninteractively,
  including after reboot. Review the owner's key/agent policy; the helper does
  not generate, unlock, export or replace GPG keys. Inspect available fingerprints
  with `gpg --list-secret-keys --with-subkey-fingerprint` as that owner.
- A source checkout and access to build its existing `docker/Dockerfile` and
  download the RabbitMQ and Caddy images. No separate controller image is needed.
- One controller per Podman owner. Resource names are fixed; another deployment's
  containers, network, volumes or systemd units cause a refusal, not replacement.
- SQLite with one Web deployment and shared application data. This helper does
  not provision a MariaDB profile, import Docker volumes or migrate an existing
  package/Compose installation.
- Start all commands as the same owner, with the same state and unit directories.
  Root uses system units; an ordinary login account uses user units. Never run
  half of a rootless installation with `sudo`.

The helper uses the current owner's Podman engine directly. It does not mount an
engine socket or grant the web application control over the host's containers.
SELinux remains enabled; managed mounts carry shared/private labels and named
volumes use ownership adjustment for their container users.

Rootless bridge networking must also work immediately after a host reboot,
without first starting a rootful container. On the qualified Rocky Linux 9.8
host, Netavark 1.17.2 used legacy iptables and required the administrator to load
`ip_tables`, `iptable_nat`, `iptable_filter` and `iptable_mangle` at boot. An
unprivileged user cannot load missing host kernel modules. Review the selected
network backend and the host's `/etc/modules-load.d/` policy; the deployment
helper does not change that policy.

When Docker is already installed, its host forwarding policy can also block a
rootful Podman bridge. The Debian qualification host required explicitly scoped
bridge traffic/egress/reply rules under its existing `FORWARD=DROP` policy. Keep
the host's security policy intact and review the actual bridge and uplink names.
The helper does not flush firewall rules, disable Docker or change global policy.

## First start

From the checkout, for a system deployment:

```sh
sudo python3 podman/deploy.py prepare --build --gpg-fingerprint GPG_FINGERPRINT
sudo python3 podman/deploy.py start
sudo python3 podman/deploy.py password
```

Replace `GPG_FINGERPRINT` with the full fingerprint of the owning account's key
(40 or 64 hexadecimal characters). For a system deployment this is root's key;
for rootless deployment it is the login owner's key. Later runs read the public
fingerprint from the private state manifest and reuse the existing encrypted
secrets. An unavailable key is an error; there is no plaintext fallback.

`prepare` builds the existing application image and writes the units and private
state, but does not start the application. Inspect `/etc/containers/systemd/roxywi-*`
and `/var/lib/roxy-wi-quadlet` before `start`. The application image is pinned to
the locally resolved immutable image ID, persisted as `image_id` in `settings.json`.
Ordinary `start` reuses that ID even when its original tag moves or all roles are
stopped. Changing the image, building again or changing deployment options requires
`upgrade`; settings from older helper versions without an image ID require an explicit
`upgrade` before ordinary startup. To supply a locally available image
instead, use `prepare --image IMAGE`; the helper does not pull an absent
application image implicitly.

For rootless deployment, log in as the intended owner and run:

```sh
python3 podman/deploy.py prepare --build --gpg-fingerprint GPG_FINGERPRINT
python3 podman/deploy.py start
python3 podman/deploy.py password
```

Rootless state defaults to `~/.local/share/roxy-wi-quadlet` and units to
`~/.config/containers/systemd`. An administrator must enable lingering for that
account if its user manager should start at boot and remain after logout:
`sudo loginctl enable-linger USER`. Review the account's permissions first.

Open **https://localhost:8443** and sign in as `admin` with the generated password.
The default published port binds only `127.0.0.1`. Caddy generates a local
evaluation CA. Trust its public root certificate only on evaluation clients that
need it; the helper does not modify the host trust store. Its own readiness probe
verifies the HTTPS hostname and certificate against that deployment's public CA,
then checks `/health/ready` as well as all four application roles. Three consecutive
successful checks are required before startup is reported as ready.

For a remote evaluation host, forward its loopback port over SSH, for example
`ssh -L 8443:127.0.0.1:8443 USER@HOST`, then use the same localhost URL.
An explicitly exposed evaluation endpoint can instead be prepared with:

```sh
sudo python3 podman/deploy.py prepare --build --gpg-fingerprint GPG_FINGERPRINT \
  --public-url https://roxywi.example.test:8443 --bind 192.0.2.10:8443
```

Replace the documentation address and hostname; DNS must resolve to that host
from the controller for readiness verification. Only HTTPS origins and explicit
bind IP addresses are accepted. Firewall and external DNS remain operator setup.
Changing the URL after initial preparation also requires reviewing the preserved
`Caddyfile`. Replacing the evaluation TLS profile with a public certificate needs
an adjusted readiness trust strategy; that is outside this helper's profile.

## Operation and upgrades

```sh
sudo python3 podman/deploy.py status
sudo python3 podman/deploy.py logs
sudo python3 podman/deploy.py stop
sudo python3 podman/deploy.py start
```

Omit `sudo` for a rootless deployment. Logs are read from the owning systemd
journal. The Roxy-WI tools page identifies this mode as **Podman Quadlet**;
controller lifecycle belongs to systemd and is unavailable through the web page.
Generated units have boot targets; do not `systemctl enable` generated services.

Before upgrading, stop the controller and back up its persistent volumes and
private state together using the same Podman owner. Keep the previous application
image available. From the updated source checkout, run:

```sh
sudo python3 podman/deploy.py upgrade --build
```

Upgrade builds and pins the replacement image, stops the application roles and
HTTPS endpoint, reruns the database migration as a oneshot unit, then starts the
roles and verifies readiness. **There is downtime.** The broker data is retained.
An ordinary `start` resumes missing roles without replacing an active deployment;
use `upgrade` for changes to its image or options. When all application roles are
inactive, `start` resets the completed migration oneshot and runs migration from
the pinned image before starting the roles. Upgrade stops the previous deployment
and migration before replacing units or persisting its new pin.

Container stop timeouts are explicit: Operations gets 1,800 seconds to drain,
other application roles and migration get 300 seconds, RabbitMQ gets 120 seconds,
and Caddy gets 30 seconds. Each systemd stop budget is 60 seconds longer than
the corresponding Podman timeout to allow cleanup.

Startup failure retains the data, units and secrets for inspection. Check
`status` and `logs`; no automatic database rollback is attempted. A schema
rollback requires restoring the matching database backup and original image,
not merely changing an image tag.

## Persistent state and recovery

The private state directory (0700) contains `secrets.json` (a **public metadata
manifest**, not secret values), `encrypted-secrets/`, `settings.json`, `roxy-wi.cfg`
and `Caddyfile`. Secret material is created through standard input to native
`podman secret create --driver=pass`, which stores GPG-encrypted data. Units use
`Secret=` references to provide only the required values to each container at
runtime. No plaintext `app.env`, `broker.env` or JSON secret bundle is written.
The broker receives its password only; it does not receive the application keys.
The Podman owner and privileged administrators can access running secrets; this
protects stored secret material, not a compromised owning account.

Existing application and HTTPS configuration files are preserved on regeneration.
The metadata manifest is 0600 and the encrypted store is 0700. Secret ownership
labels, encrypted driver, storage location and original key fingerprint are
verified before reuse. Missing or undecipherable secrets are never regenerated
for an initialized deployment. A partially prepared new deployment can resume
without replacing secrets already created.

Named volumes are `roxywi-app-data`, `roxywi-broker-data`, `roxywi-tls-data` and
`roxywi-tls-config`. Application data includes the SQLite database, uploaded keys,
certificates and configuration history. **The original application encryption
secret and the GPG key needed to decrypt it must be recoverable.** Back up the
state directory, Podman secret metadata/storage, persistent volumes and the
owner's GPG recovery material together, following your key-protection policy.
Test restoration and noninteractive decryption before relying on reboot recovery.
Do not commit or share private keys, secret exports or administrator password
output.

An earlier evaluation deployment with plaintext `secrets.json`/environment files
is refused without altering its keys or units. Do not delete its state to bypass
the check: a reviewed migration retaining its exact application encryption key
is required. This helper does not silently adopt or rotate those credentials.

Resources carry an ownership label derived from the state directory. Restoring
requires the original state directory path, engine owner, state files and
matching volumes. Existing labeled data with missing secrets is rejected before
new keys can be generated. Symlinked state/configuration and unrelated units or
unlabeled resources are refused. `stop` does not remove volumes or secrets.
There is deliberately no destructive cleanup command or automatic adoption of
unrelated data.

## Reproduce automated checks

```sh
python3 -m pytest tests/unit/runtime/test_podman_controller_quadlet.py -q --no-cov
test -x /usr/lib/systemd/system-generators/podman-system-generator
python3 -m pytest tests/integration/test_podman_quadlet_linux.py -q --no-cov
```

The integration test uses `QUADLET_UNIT_DIRS` and the real generator's `--dryrun`
in a temporary directory. It also creates a disposable GPG encryption key and
an isolated Podman storage root, exercises the real `pass` driver, verifies
repeatable reuse and checks that plaintext secret values do not appear in the
state or engine metadata files. The generation test starts no services.
Set `ROXYWI_TEST_PODMAN_DRAIN=1` to also run a disposable, isolated-store
container whose SIGTERM handler takes 12 seconds to complete. This verifies the
generated Operations stop timeout without overriding `podman stop` timeout.
It requires a working Podman init helper and pulls Alpine into the temporary store.
GitHub Linux integration enables this test; existing controller services are untouched. GitHub's Linux integration job
installs Podman and requires the generator, preventing a skipped test from being
mistaken for validation. Live Debian/EL qualification must additionally cover
rootful/rootless startup, SELinux on EL, all workers, browser login, reboot,
upgrades, persistent credentials and failure/recovery before leaving draft.

## Recorded live qualification

On 29 October 2026, the combined feature snapshot was exercised on disposable
Proxmox VMs. These are the observed profiles, not a claim that every supported
distribution version has been tested:

| Host | Podman | Engine owners | Observed lifecycle |
| --- | --- | --- | --- |
| Debian 13.7, systemd 257 | 5.4.2 | root and ordinary login user | Startup, four application roles, RabbitMQ, verified HTTPS, real login, same-image upgrade, boot start, encrypted data retention |
| Rocky Linux 9.8, systemd 252, SELinux enforcing | 5.8.2 | root and ordinary login user | Same lifecycle, including isolated rootless boot after the host prerequisites above were configured |

Each engine used its own locally generated disposable GPG key and encrypted
Podman secret store. An SSH private key was not copied between hosts. A dummy
SSH-password credential was created through the real HTTP API; after upgrade and
reboot it still decrypted correctly, its SQLite value remained ciphertext, and
the original Podman secrets remained unchanged. `upgrade` reused the same image
to exercise shutdown, migration and restart; it did not test a schema change
between released application versions.

Rootless failure/recovery was also exercised on both hosts: temporarily removing
the public deployment manifest made `start` refuse the initialized deployment
without generating replacement secrets. Restoring the original manifest allowed
verified startup with the same secrets and credential. Persistent data and keys
were retained throughout. This is not a full backup/restore or cross-version
database rollback qualification.

The actual Quadlet generators on Podman 4.9.3, 5.4.2 and 5.8.2 were checked for
mount paths containing spaces. Newer generators use systemd C escapes in their
generated commands; the regression comparison accounts for that representation.

### Shutdown and image-selection review follow-up

The 29 October follow-up adds explicit container/systemd stop budgets and a
persisted application image pin. Seventy focused CLI/queue/lifecycle regressions
passed locally, including moved-tag startup, an active completed migration,
explicit upgrade ordering and legacy unpinned settings. Three native tests passed
on the isolated Debian 13 / Podman 5.4.2 lab: encrypted-secret reuse, generated
units for all seven services and the real 12-second SIGTERM drain with exit 0.
The native run used an independent rootful storage root. The minimal host's
missing init helper was extracted into the test directory and supplied only
through that test's PATH. No host package, controller service or global
configuration was changed. This focused follow-up does not repeat the older
full rootful/rootless Debian/Rocky startup and reboot qualification above.
