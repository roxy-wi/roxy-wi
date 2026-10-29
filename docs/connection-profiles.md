# Shared connection profiles

Open **Admin area → Connection profiles** to create a named outbound connection.
Profiles belong to one group; a super administrator can also create a profile
shared across groups. Operators can list profiles available to their group.
Group administrators can manage their group's profiles, while shared profiles
are managed by a super administrator.

The supported transports are TCP with TLS (the default), plain TCP, UDP and
HTTPS. HTTP Basic, Bearer and API-key authentication are available for HTTPS
receivers. TCP/UDP syslog has no generic username/password login. Both TLS
transports support a custom trusted CA and a client certificate/private key for
mutual TLS. A client certificate can also be combined with HTTPS authentication.
Server certificate and hostname validation remain enabled. TLS failures never
fall back to plaintext.

For TCP consumers the profile also specifies octet-counting or newline framing.
The connection checker itself sends no application message on TCP. UDP cannot
prove connectivity or delivery, so its check reports **unverified** and sends no
test datagram. HTTPS checks issue a single HEAD request with the configured
authentication, without following redirects or publishing the response body.
A receiver may support event POST requests while rejecting HEAD; its response is
shown without claiming that an audit event was accepted or archived.

## Credentials and revisions

Credential and PEM fields are encrypted with the same configured Fernet key
used by Roxy-WI credentials. Every process consuming a profile must have the
correct deployment key. Secrets are never returned by the profile API. The UI
shows only whether each field is configured. Leave a field empty when editing
to preserve its value; select **Clear saved value** to remove it explicitly.
Changing authentication or turning off TLS requires explicitly clearing
incompatible saved credentials. Changing the destination or authentication identity
(host, port, full HTTPS URL, transport, username or API-key header) also requires
re-entering or clearing retained passwords, tokens and client certificate/key
material; a hidden credential cannot be silently redirected to a new target.
Renaming a profile or changing its timeout/framing keeps compatible credentials.

Saving uses an optimistic revision check to prevent overwriting another edit.
Each revision preserves its settings and encrypted credentials for consumers
that pin a revision. Disabling a profile prevents resolving any of its revisions.
A profile registered as in use cannot be deleted; disable it instead. Existing
references must be released deliberately by their owning integration. The
credential-key rotation command includes both current and historical profiles.
Owned profiles hold a restricted reference to their group: retire their consumer
references and delete the profiles before deleting that group. This prevents a
new group reusing an old numeric ID from inheriting hidden credentials. Refused
group deletion leaves its OIDC mappings, membership and settings intact.

This change provides reusable connection storage and connection checking.
Integrations bind their use through the backend adapter; it does not silently
replace existing SSH profiles, notification settings or webhook credentials.

## Backend integration

`app.modules.integrations.connection_profiles.resolve(profile_id, group_id,
revision=...)` returns a `ResolvedConnection` for a trusted backend consumer.
Always derive `group_id` from the authenticated request or authorized task, not
from an untrusted request field. Credentials are excluded from its repr, but
callers must still avoid serializing the credentials dictionary into logs.

Use `bind_use(profile_id, group_id, consumer=..., consumer_id=...)` in the same
transaction that persists a consumer reference. This serializes against profile
deletion, checks visibility/enabled state and returns the selected revision.
Do not grant callers a public endpoint that simply exposes `resolve()`.

An integration must choose explicitly how queued work uses revisions. Updating
the profile must not silently redirect already queued events to another receiver.
This API preserves revisions; the consuming integration owns retry/requeue policy.

## HTTP management API

The browser uses interactive cookie authentication and CSRF-protected
`/admin/connection-profiles` endpoints. Header-only or mixed Authorization/cookie
identities are rejected on this management surface. GET lists visible metadata. POST creates a profile, PUT on `/<id>`
updates it and DELETE on `/<id>` removes an unused profile. Updates and deletes
require the current revision. POST on `/<id>/test` checks a saved, enabled profile.

Creation and update accept a flat document such as:

```json
{
  "name": "Central audit",
  "group_id": 1,
  "transport": "https",
  "url": "https://audit.example.test/events",
  "auth": "bearer",
  "secrets": {"token": "SUPPLY_THE_RECEIVER_TOKEN"}
}
```

For updates include `revision`. The `secrets` object is a write-only patch;
`clear_secrets` is an explicit list of fields to remove. Neither is a public
response field. Public responses contain a `settings` object and boolean
`configured` flags. Group scope 0 is reserved for shared profiles.

Connection checks are administrator actions because they open an outbound
connection to a chosen destination. They resolve and validate all DNS addresses
before connecting to a pinned address, reject link-local/metadata, multicast and
unspecified destinations, and do not use ambient proxy settings. Intended private
and loopback receivers are supported. The socket timeout is shared across address
attempts; native DNS resolution also depends on the deployment's resolver timeout.

## Validation

Focused product tests cover group/role isolation, secret preservation, encrypted
storage, key rotation, revision conflicts, deactivation, use references and
invalid input. Loopback TLS tests verify actual Basic/Bearer/API-key headers,
untrusted-certificate rejection and credential isolation on redirects. Browser
tests exercise creating, editing and checking a profile without reading its
password back, plus safe rendering of names.

```sh
python -m pytest tests/product/test_connection_profiles.py \
  tests/integration/test_connection_profile_transport.py \
  tests/security/test_secret_rotation.py -q --no-cov
ROXYWI_TEST_BROWSER=1 python -m pytest \
  tests/product/browser/test_connection_profiles_browser.py -q --no-cov
```
