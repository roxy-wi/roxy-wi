# Personal API tokens

Open **your user name → Personal API tokens** to create a separate credential for
each integration. This feature uses existing local accounts and does not require
an identity provider. A token is a JWT carried as `Authorization: Bearer <token>`
**over HTTPS**, but is a separate API credential checked against its own database
record on every request. It cannot authenticate the web interface, create another
token, change authentication settings or widen its group through API parameters.
Unmapped endpoints/methods are denied by default.

## Create, use and revoke

Select only required permissions, enter your current password and choose an expiry
from 1 to 365 days (default 90). No permissions are selected by default. Each token
has one fixed group where its owner must remain a member. Switch the GUI's active
group before creating a token for another group; the resulting token continues to
use its fixed group when you later switch the web session. Tokens never change
the owner's web group.

Copy the token on creation into your integration's protected secret store. The
application displays its value only once, never lists it again, and does not put
it in an URL, browser cookie or browser storage. Hide token, navigation or reload
clears the displayed value. The database stores a SHA-256 digest of the complete
credential, with a random 256-bit nonce in its signed payload. Treat the displayed
JWT as a password; it is not an access token returned for a human web login.

Example, with the secret provided by your integration's secret manager:

```sh
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${ROXYWI_PERSONAL_TOKEN}" \
  https://roxy.example.test/api/servers
```

The value is never sent in a query string. The example assumes a valid receiver
certificate and does not disable HTTPS verification.

Revoke stops subsequent requests immediately, without waiting for JWT expiry.
Already authorized/in-flight requests and queued operations are not cancelled.
The owner can revoke only their own tokens. Deleting an account cascades its
tokens and authentication gate, so reusing a numeric user ID cannot inherit its
credentials, even if a password hash is imported unchanged. Deleting a group also
revokes its scoped credentials through a cascading reference, so reusing a group
ID cannot transfer a previous group’s personal tokens. An administrator can disable an
account, remove its group membership or reset its password to invalidate its API
credentials. Changing/rehashing the stored password also invalidates existing
personal tokens conservatively, including migration from a legacy password hash.
Changing the JWT signing key invalidates these JWTs as well. SSH/Fernet credential
key rotation does not invalidate personal API tokens.

Current implementation requires a **local account with a stored password**.
LDAP-only and OIDC-only accounts without a local password cannot create these
credentials. The existing OIDC login flow remains unchanged. With the local
security feature installed, creation delegates to its sensitive-action proof:
password plus configured TOTP, or a one-use reauthentication proof from a passkey.
The feature also checks the security epoch on each token use, so MFA recovery or
security reset can revoke old credentials. These are optional integration
contracts; this PR works independently without either MFA PR.

## Permissions

A token receives the intersection of its scopes and the owner's **current** role,
group membership, service permissions and existing subscription/API entitlement.
Adding a scope never grants a higher role. Revocation and permission changes are
read from the database, without an authority cache across requests. Service and
change targets are checked against the fixed group, including rollout selections
and implicitly discovered master/slave topology before a draft captures any
remote configuration or returns a rollout preview.

| Scope | Allowed use |
| --- | --- |
| `inventory.read` | List/read servers in the fixed group. Existing administrator role requirement still applies. |
| `services.read` | Read service/backend and queued operation status. |
| `config.read` | Read remote configuration files and version history; configurations may contain application secrets. |
| `changes.read` | Read group changes, their configuration diffs, events, statistics and reports. |
| `changes.write` | Create/edit drafts and request validation; cannot directly write a live config or deploy. |
| `changes.approve` | Approve under the existing administrator and distinct-author rules. Two tokens of one author are still the same author. |
| `changes.deploy` | Deploy/rollback, control/recover rollouts, schedule/cancel them and request drift checks. |
| `services.control` | Start, stop, reload or restart a managed service. |

There is no wildcard scope. Credentials, users/groups, instance settings,
installation, token management and webhook administration are outside this initial
allowlist. This deliberately does not promise access to every existing API route.
New routes must explicitly opt into the map in `app/modules/api_tokens/scopes.py`.
The existing API license checks remain in place, including for otherwise valid
credentials. The public password login endpoint still authenticates independently;
a personal token alone does not satisfy that login. When MFA is installed, that
login must complete MFA before issuing a human access token.

When external audit export is also installed, credential creation/revocation
records `auth.personal_token.created` / `auth.personal_token.revoked` with the
public metadata ID and owner/group context. The initial export uses this stable
ID for correlation and does not include arbitrary user-entered token names.
Authenticated API request events can be correlated by that ID, without exporting
the bearer credential. A failed credential audit write
rolls back creation/revocation rather than reporting an unrecorded change.

## Local data and limits

Personal token metadata includes owner, group, name, scopes, created/expiry/revoked
and last-used timestamps, password version and optional security epoch. Metadata
is owner-only even for a super administrator using the personal-management page.
The GUI marks records unavailable when the current owner credential/security
version or group membership no longer permits use; individual operation rights
still depend on the live role and service ACL. Last-used writes are throttled to once per minute and are best effort; that field
is not an authorization cache. The credential digest/versions are never returned
through the management API.

At most 25 active tokens and 250 retained records are allowed per user. Scheduler
removes up to 1000 metadata records per hour when they have been expired or revoked
for 90 days. A missing metadata record always rejects the token. A shared database
gate permits five failed sensitive authentication attempts per five minutes,
including across web workers. The gate has an account-incarnation nonce and
issuance rechecks credentials and membership under the account lock, so a proof
in flight cannot transfer to a deleted/recreated account or survive a reset; successful creation resets that gate. A valid web
session remains required, and cookie CSRF protection applies to creation/revocation.
Do not attach an Authorization header to the interactive management requests;
mixed cookie/header identities are rejected.

Management endpoints are `GET/POST /user/personal-tokens`,
`DELETE /user/personal-tokens/<id>` and `GET /user/api-access`. All require the
interactive cookie session. The creation response has an `access_token` shown
once plus public `token` metadata, with `Cache-Control: no-store`. Creation body:

```json
{
  "name": "CI inventory", "group_id": 1,
  "scopes": ["inventory.read"], "expires_days": 90,
  "password": "<interactive password>"
}
```

The field value above is a documentation placeholder. Do not commit real tokens,
passwords or authorization headers to configuration repositories. Use the normal
protected database backup; schema rollback refuses to silently erase credential
metadata. Existing `/api/login` JWT clients continue to work with their existing
role/group behavior; personal token validation does not convert them to scoped
credentials or change the browser's active group rules.

## Verification

Product tests use real authentication/routes/database for show-once storage,
revocation, expiry, live role/group/service/password changes, fixed-group isolation
through query and target IDs, cookie/header ambiguity, CSRF, shared authentication
throttling (including concurrent workers), endpoint default-deny, service control,
owner-only metadata, independent approval, concurrent credential reset and
optional security-epoch integration. Migration is idempotent and
retention cannot reactivate credentials. Browser tests create a token, use it for
a real API request, hide/revoke it, check reload and test HTML-safe names.
[UI screenshots](screenshots/personal-tokens/README.md) use synthetic data with the
actual credential hidden. Real Debian/EL qualification follows draft publication;
it is not implied by these local tests.
