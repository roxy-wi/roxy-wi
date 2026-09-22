# Configuration and authentication

> Applies to **Roxy-WI 9.1 and later**.

Login at `https://roxy-wi-server/admin`, then add users, groups, and servers. Set the initial admin password with `ROXYWI_BOOTSTRAP_ADMIN_PASSWORD` (at least 12 characters). If it is not set, Roxy-WI creates `/var/lib/roxy-wi/bootstrap-admin-password` with mode `0600` on first start.

Fresh installations generate random HAProxy, NGINX, Apache statistics passwords. Set `ROXYWI_RABBITMQ_PASSWORD` (at least 12 characters) before the first start when RabbitMQ is configured separately; otherwise a random value is stored in the admin settings.

Store a unique Fernet key as `[main] secret_phrase` in `/etc/roxy-wi/roxy-wi.cfg`. `ROXYWI_SECRET_PHRASE` is an optional override and, when non-empty, takes precedence over the config file. Existing installations must keep their current unique key; no credential rotation is required during a normal code upgrade. Rotate only when deliberately replacing a key: set the previous key as `ROXYWI_OLD_SECRET_PHRASE`, the replacement as `ROXYWI_SECRET_PHRASE`, and run `python3 rotate_credential_secret.py` once before restarting the application. Install the TLS certificate and private key as `/etc/roxy-wi/certs/roxy-wi.crt` and `/etc/roxy-wi/certs/roxy-wi.key`; the private key must not be stored below the web application root. SSH connections automatically accept previously unknown host keys; a changed key that conflicts with a known key is still rejected.

## Scheduler

The scheduler HTTP API is permanently disabled. Web workers do not start background jobs by default, which prevents the same job from running once per worker. Run exactly one dedicated scheduler process under your service manager:

```shell
python3 scheduler_runner.py
```

`scheduler_runner.py` enables `ROXYWI_SCHEDULER_ENABLED=1` for that process. Do not set this variable globally for the web service.

## OpenID Connect

Super administrators can configure one or more OIDC providers under **Admin → OIDC**. Roxy-WI supports discovery metadata, signed ID token validation through JWKS, optional UserInfo claims, verified-email/domain policies, automatic user creation or email linking, and external-group mappings to Roxy-WI groups and roles. Local and LDAP login remain available.

When Roxy-WI is behind a reverse proxy, set `ROXYWI_PUBLIC_URL` to its canonical external origin, without a trailing slash, for example `https://roxy-wi.example.com`. Register the callback URL shown in the provider form at the identity provider. The usual scopes are `openid email profile`; add the provider-specific groups scope when group mapping is used.

OIDC client secrets are encrypted with the existing `[main] secret_phrase` Fernet key. Keep the same key during a normal upgrade; no new key or credential rotation is required.

See [operations](operations.md) for process management and [plans](plans.md) for feature availability.
