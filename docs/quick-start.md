# Try Roxy-WI locally

> Applies to **Roxy-WI 9.1 and later**.

Run Roxy-WI on your own machine with Docker Compose.
For Linux packages, use the [installation guide](https://roxy-wi.org/installation).
For a browser-only tour, use the [shared demo](https://demo.roxy-wi.org).

## Requirements

- Git and Python 3.10 or newer; the launcher uses only Python's standard library.
- Docker Engine or Docker Desktop configured for Linux containers.
- Docker Compose 2.24.4 or newer and an available local port 8443.
- Network access to download images, Python dependencies and Ansible roles during the build.

## Start

Run from the repository root:

```sh
git clone https://github.com/roxy-wi/roxy-wi.git
cd roxy-wi
python3 docker/quickstart.py start
python3 docker/quickstart.py password
```

On Windows, use `py -3` instead of `python3` if that is how Python is installed.

Open **https://localhost:8443**. Caddy creates a local HTTPS certificate, so the
browser will initially report an untrusted issuer. Accept it for this local
evaluation. The launcher does not modify your machine's certificate trust store.
Sign in as **admin** with the generated initial password printed by the second
command. If you have already changed the password in Roxy-WI, use the new one.

The launcher builds the current source, runs migrations, and starts Web, Scheduler,
Service Events, Operations, RabbitMQ and the HTTPS proxy. It uses a separate Compose
project named `roxywi-quickstart`; only the HTTPS proxy is published, on loopback.

## Connect your first server

1. Use a test server reachable from the Docker network, with SSH and a service
   you want to manage. `localhost` inside a container is the container itself.
2. Open **Admin → SSH credentials** and add the credentials for that server.
3. Open **Admin → Servers**, add the server to your group and assign its credentials.
4. Check the service's configuration paths in Settings, then open the server's
   service view or configuration editor to verify access.
5. When access works, follow the [Change Center tour](change-center-tour.md) on
   that test setup. Change Center requires Premium; starting the local stack does
   not activate a subscription or connect demonstration servers automatically.

See [plans](plans.md) for monitoring and other subscription requirements.

## Inspect and stop

```sh
python3 docker/quickstart.py status
python3 docker/quickstart.py logs
python3 docker/quickstart.py stop
```

`stop` removes the evaluation containers and network, but preserves volumes and
`docker/.env.quickstart`. Running `start` again reuses the database and secrets.
Do not delete or regenerate that file while retaining the database: it contains
the key used to decrypt stored credentials. It is ignored by Git and created with
owner-only permissions on POSIX systems.

## If startup fails

Check that Docker is running with Linux containers, Compose meets the minimum
version, and port 8443 is free. Inspect `status` and `logs` for a failed migration
or dependency. The first build can take longer because it downloads dependencies.
Do not run database initialization scripts to fix an unrelated HTTP 500 error.

The quick start is for local evaluation. For a deployment reachable by other users,
use a real hostname and trusted HTTPS certificate, configure persistent backups,
and follow [deployment](deployment.md) and [operations](operations.md).

The [Container workflow](../.github/workflows/container.yml) exercises this launcher,
HTTPS login and a restart with the same secrets. Local unit tests also check that
an existing environment cannot be silently replaced.
