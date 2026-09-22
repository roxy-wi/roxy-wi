# Deploy Roxy-WI

> Applies to **Roxy-WI 9.1 and later**.

Choose [Linux packages](https://roxy-wi.org/installation), Docker Compose or
Kubernetes. For a first look on your laptop, the [quick start](quick-start.md)
provides local HTTPS and generates its own persistent secrets.

## Process roles

Roxy-WI runs four application roles against one database and shared application
storage. RabbitMQ carries background work between processes.

| Role | Responsibility |
| --- | --- |
| Web | Serve the interface and API. |
| Scheduler | Queue scheduled checks, backups, certificate work and Change Center deployments/drift checks; run exactly one instance. |
| Service Events | Consume service events. |
| Operations | Execute queued actions and record their progress and results. |
| Migrate | Initialize or update the database, then exit before application roles start. |

The common entry point is `python3 roxy_wi.py ROLE`; role names are `web`,
`scheduler`, `service-events`, `operations` and `migrate`. Packages and container
manifests supply the process supervision. Web workers must not also start Scheduler.

## Linux packages

The [package workflow](../.github/workflows/native-packages.yml) builds DEB and
EL9/EL10 RPM packages and verifies them on Ubuntu 24.04, Debian 12/13 and Rocky
Linux 9/10. Use the [installation guide](https://roxy-wi.org/installation) for
repository configuration and package installation on those platforms. Apply
updates with the [package update guide](https://roxy-wi.org/update-guide).

Keep the configured database, `lib_path`, configuration files and encryption key
when restarting or updating. See [operations](operations.md) for what to preserve
and how to check each application role.

## Docker Compose

The repository includes [MariaDB](../docker/docker-compose.yml) and
[SQLite](../docker/docker-compose.sqlite.yml) manifests. These build the application
from your checkout; use the MariaDB manifest for the commands below. Keep the same
project name, environment file and manifest for all subsequent commands.

1. Copy `docker/.env.example` to `docker/.env` and replace every placeholder.
   Set `ROXYWI_PUBLIC_URL` to your external HTTPS origin, without a trailing slash.
   Generate distinct random passwords and an application secret of at least
   32 characters. Generate a Fernet key for `ROXYWI_SECRET_PHRASE` with:

   ```sh
   python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   ```

   Keep the environment file private and outside version control. Preserve it
   with your database backups: encrypted credentials depend on this key.
2. Put Web behind an HTTPS reverse proxy. The base manifest publishes port 8080;
   restrict access to that port to the proxy and configure the proxy trust settings
   for your network. Use a hostname with a trusted certificate for shared access.
3. Build and start the stack:

   ```sh
   docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml up --build --detach --wait --wait-timeout 300
   ```

   The migration container must succeed before application containers start.
4. Read the generated initial password and log in as `admin`:

   ```sh
   docker compose --project-name roxy-wi --env-file docker/.env -f docker/docker-compose.yml exec -T web cat /var/lib/roxy-wi/bootstrap-admin-password
   ```

   Change the password after signing in. The file contains the initial password;
   it does not track later password changes.

Named volumes retain application files, database data and RabbitMQ state. Do not
use `down --volumes` when stopping an installation you intend to keep. Container
processes use UID/GID 10001 for application storage; bind mounts must be writable
by that user.

## Kubernetes

Use the [Helm chart](../helm/roxy-wi) and its
[values reference](../helm/roxy-wi/values.yaml). Build the application image from
the checkout, publish it to a registry available to your cluster, and set
`image.repository` and `image.tag` to that image.

Provide a database, RabbitMQ, secrets, persistent storage and an HTTPS ingress.
The chart does not install a database or message broker. Review these values:

| Setting | Purpose |
| --- | --- |
| `config.main.public_url` | External HTTPS origin used by authentication. |
| `existingConfigSecret` | Supply a private `roxy-wi.cfg` instead of placing secrets in the values file. |
| `rabbitmq.existingSecret` | Supply `ROXYWI_RABBITMQ_HOST`, `ROXYWI_RABBITMQ_PORT`, `ROXYWI_RABBITMQ_VHOST`, `ROXYWI_RABBITMQ_USER` and `ROXYWI_RABBITMQ_PASSWORD` as Secret keys. |
| `persistence.existingClaim` | Mount existing application storage. |
| `config.database.engine` | Use `mysql` with an external MariaDB/MySQL database for HA. |
| `web.replicaCount` | Keep one web replica with SQLite. |
| `ingress` | Configure your ingress class, host and TLS secret. |

Save your deployment values to a private file, then render and inspect before
installing:

```sh
helm lint helm/roxy-wi -f /secure/path/roxy-wi-values.yaml
helm template roxy-wi helm/roxy-wi --namespace roxy-wi -f /secure/path/roxy-wi-values.yaml
helm upgrade --install roxy-wi helm/roxy-wi --namespace roxy-wi --create-namespace -f /secure/path/roxy-wi-values.yaml --wait --timeout 10m
```

Rendered manifests can contain secrets; keep their output private. The migration
Job initializes the schema, and application init containers wait for database
readiness. For upgrades, stop application writers while applying schema changes.

All roles need access to the same application files. Multi-node deployments need
storage supporting shared access and advisory file locks; ReadWriteOnce storage
also requires compatible pod placement. Keep one Scheduler. Review
[backup storage](configuration-backups.md) and [LE state](letsencrypt.md) before
scaling Operations.

[Documentation index](README.md) · [Operations](operations.md)
