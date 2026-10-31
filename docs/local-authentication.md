# Local authenticator MFA

Local TOTP protects password accounts independently of OpenID Connect, LDAP,
subscriptions and external authentication services. Existing OIDC sessions remain
provider-owned; their identity provider remains responsible for their MFA policy.
The licensed API operations retain their existing subscription checks.

Open **Account security** using the shield beside the signed-in account. Set up
an authenticator, scan the locally generated QR or enter the setup key, then
confirm a current six-digit code. Nothing is activated until confirmation.
Save the ten recovery codes offline when shown. They are shown once, contain
128 random bits each, work once, and replace the previous set when regenerated.
The UI clears the setup key/QR after confirmation or cancellation and never
stores passwords, codes or one-use proofs in browser storage.

TOTP uses PyOTP 2.10.0 with the RFC 6238 interoperable six-digit SHA-1/30-second
profile and a ±1-step window. The last accepted counter is updated conditionally;
a code at an already accepted or older counter cannot be reused, even on another
worker. Keep the host clock synchronized. QR rendering uses the installed
`qrcode` library; secrets are never sent to an external QR service.

## Policy and enrollment

A super administrator can choose Optional, Local administrators, or All local
accounts. The administrator policy includes role 1 or 2 in **any current group
membership**, including inactive groups. The policy editor uses the current
active group's role-1 membership, like other instance administration controls.
The administrator enabling a requirement must first configure their own factor.
Enrollment grace is explicitly 1–30 days (default seven days).

Changing policy invalidates existing sessions and personal tokens. During grace,
password users can sign in and enroll. After grace, password verification for an
unenrolled account yields only a short-lived enrollment challenge. Successful
confirmation then activates the factor and issues the first full login. A session
whose grace expires can use only the account-security status, setup,
reauthentication and logout surfaces; normal pages and API operations reject it.
This permits enrollment without granting a general application session.

Adding/removing a factor, regenerating recovery codes, editing policy and issuing
personal tokens require a fresh password plus an existing second factor, or a
purpose-bound one-use reauthentication proof. A passkey provider, when installed,
can supply that proof after user verification. To replace a lost authenticator, use **Replace authenticator** with the local
password and a recovery code. The old factor remains active until the new setup
is confirmed; replacement changes the security generation and recovery-code set.
The final factor cannot be removed
while the account is covered by a required policy. Reauthentication proofs expire
after two minutes and are bound to the current session and the requested action.
All cookie management endpoints enforce CSRF and reject Authorization headers,
including mixed cookie/header identities.

## Web and API login

`POST /login` keeps its existing password fields. For an enabled factor it returns
HTTP 202 with `status=mfa_required`, an opaque `challenge`, and available methods;
it sets no authentication cookie. Required enrollment returns
`status=enrollment_required`. The browser displays the next step automatically.

`POST /api/login` likewise returns HTTP 202 instead of a full JWT for protected
accounts. Complete it with:

```http
POST /auth/login/complete
Content-Type: application/json

{"channel":"api","challenge":"<opaque password challenge>","otp":"<six digits>"}
```

Use `recovery_code` instead of `otp` for one-use recovery. Only successful
completion returns `access_token`. API enrollment uses
`/auth/enrollment/start` and `/auth/enrollment/confirm`, carrying `channel=api`.
The web flow binds its challenge to the signed browser session; the API flow uses
the opaque random challenge as its bearer proof. Neither challenge authorizes
other endpoints, group changes or personal-token creation.

Challenges live in the shared database, carry an encrypted payload, purpose,
account generation, password fingerprint and expiration, allow five attempts,
and are consumed atomically with a factor. At most twenty pending challenges per
account are allowed; issuing another prunes that account's used/expired rows.
A separate persistent per-account gate blocks verification for five minutes
after five failures across different challenge IDs and workers. SQLite uses an
immediate transaction; MariaDB/MySQL uses row locks and a consistent account-
then-challenge lock order.

## Revocation, recovery and backups

Sessions include a random 128-bit account incarnation, the security generation,
credential fingerprint (HMAC-SHA-256 keyed by the stable Flask application secret),
authentication
method and original authentication time. Group switching preserves this proof.
Password changes invalidate old sessions and challenges. Factor changes, policy
changes, console reset and a recovery-code login invalidate older sessions and
personal tokens. A recovery login issues its cookie/token with the newly committed
generation. Epoch snapshots captured while verifying a proof prevent a concurrent
reset from attaching an old proof to a new generation. Password and identity-provider
verification capture one account incarnation before approval; session actors and
proof completion revalidate that snapshot under the parent-account lock. Deletion
and recreation of the same numeric ID cannot inherit an earlier approval. Locks
cover the short database snapshot/commit operations; password verification and
external identity-provider requests run outside those locks.
Session validation uses a coherent read-only database snapshot and never creates
missing security or policy state; mutation and proof issuance recheck the original
principal under the parent-account lock.

Legacy sessions are accepted only for accounts captured by the one-time migration
or initial bootstrap baseline, while the account is at generation zero, its
migration-time password fingerprint is unchanged, and no factor/policy requires a
stronger login. A persistent baseline marker prevents subsequent starts or migration
reruns from whitelisting a new account that reused a deleted numeric ID. Modern
proofs also check the account incarnation, including when password hashes were
cloned. Removing the optional personal-token provider never turns a
PAT-tagged JWT into a local-session bypass.

If every device/recovery code is lost, run from the Roxy-WI host console as root,
with the same configuration and database environment as the application:

```sh
python3 local_auth_recovery.py alice --confirm-user alice --reason lost-device
```

Reasons are `lost-device`, `compromise` or `restore`. This removes local factors,
revokes recovery codes and pending challenges, and increments the security
generation. It writes a durable local account-recovery event even if external
audit delivery or its queue is unavailable. With a required policy, the next
password login enters enrollment again. Resetting factors does not reset a lost
password; use the existing administrator password recovery procedure separately.

Back up the database and its installation Fernet key together and protect them as
credentials. TOTP secrets and pending setup/challenge material are encrypted; only
recovery-code digests persist. `rotate_credential_secret.py` rotates both confirmed
TOTP secrets and pending encrypted ceremonies inside its existing transaction.
Rotating the Fernet key does not change that credential fingerprint. The public
JWT fingerprint does not provide an unkeyed offline test for a legacy password.
Local authentication events retain safe account/event/outcome/time metadata for
90 days and at most 10,000 recent rows (oldest rows are pruned on recording).
This local operational history is separate from the installed audit service's
retention and bounded export queue. An installed audit adapter additionally receives explicit safe metadata
and the owning group; no password, code, key, challenge or recovery material is
exported. For denied/failed authentication, an unavailable external audit queue is logged
with a sanitized warning while the local denial record and attempt charge commit.
Successful security changes and verified-login audit still fail closed on audit
storage failures. Security mutations use the caller's database transaction; a completed
login's audit export is not claimed to be atomic with returning its HTTP response.

After restoring an older backup, revoke sessions/tokens and inspect factors before
reopening the application. Do not deploy a pre-MFA application binary against an
instance where local factors or mandatory policy have been activated: that binary
cannot enforce them. Rollback requires a tested version that supports this schema
and enforcement, or a controlled offline recovery/migration with access disabled.
Never drop authentication tables to bypass recovery.

## Verification evidence

Product tests cover encrypted unconfirmed setup, confirmation, invalid/expired
codes, counter replay, recovery reuse, purpose/session binding, cross-challenge
limits, CSRF, both login entry points, policy grace/bootstrap, current group-role
checks, header/cookie isolation, epoch snapshots, password/reset invalidation,
rotation and idempotent migrations. Independent processes race real SQLite TOTP
and recovery-code updates. Browser tests exercise real QR setup, confirmation,
recovery display, login and regeneration in Chrome with light/dark screenshots.
The screenshots contain only synthetic enabled-state data, with all secret DOM
content cleared. MariaDB and Debian/EL VM qualification is recorded separately
after the draft PR is published; local macOS checks do not claim it.

When external audit export is installed, only completed, verified login events
may use its bounded repair reserve if the normal queue is full. Configuration
changes and denied or unverified attempts cannot consume that reserve. Exhausting
the reserve fails the login without issuing a session; local denial accounting
and the failure gate remain durable when external export is unavailable.
