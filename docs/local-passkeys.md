# Local account passkeys

Roxy-WI supports WebAuthn passkeys for local accounts, independently of the
subscription and of OIDC providers. A passkey verifies the user with the device's
PIN, biometrics or another authenticator verification method. The server stores
credential IDs, public keys, counters and names; private keys remain with the
authenticator. Password authentication for LDAP and OIDC remains provider owned.

## Configure the relying party

Install the updated requirements (`webauthn==3.0.1`, Python 3.10 or later), apply
the normal database migrations, and configure the canonical address explicitly:

```ini
[security]
webauthn_rp_id = roxy.example.test
webauthn_origins = https://roxy.example.test
```

Equivalent environment settings are `ROXYWI_WEBAUTHN_RP_ID` and
`ROXYWI_WEBAUTHN_ORIGINS`. Origins are a comma-separated list of exact HTTPS
origins, including a non-default port where applicable. The RP ID is a domain,
without a scheme or port. IP address RP IDs are rejected. Browser tests use
`https://localhost:<port>`; production should use its canonical DNS name and
trusted HTTPS certificate.

Both settings are mandatory. No origin or RP ID is inferred from `Host`,
`X-Forwarded-Host`, proxy configuration or the current request. Each allowed
origin's hostname must equal the RP ID or be a subdomain of it. Wildcards and
cross-origin/embedded ceremonies are not supported. A change to the RP ID or
origin list invalidates pending ceremonies. Changing the RP ID generally requires
registering new credentials; plan a recovery path before changing it.

## Enroll and sign in

Open **Account security**, then **Manage passkeys**. Enter a descriptive name and
choose **Add passkey**. Verify the local password for the first credential, or an
existing complete authentication factor for subsequent changes. The browser then
asks the authenticator to register a resident credential with required user
verification. Up to ten named passkeys can be registered. Existing credentials
are excluded from subsequent registration requests.

Save the ten recovery codes displayed after the first enrollment. Each code is
single use, stored as a digest, and is accepted with the account password.
Regenerating codes replaces all old codes. Codes and assertions must never be
copied into tickets, screenshots or application logs.

The login page offers **Sign in with a passkey** after entering the username.
This verifies the passkey without requiring the password. Password login for an
account with a configured factor instead returns a short-lived second-factor
challenge; **Use passkey** completes that challenge. A password alone cannot
issue a web session or an API token once a local factor is configured.
`POST /api/login` returns HTTP 202 with the factor challenge instead of a JWT.
A client can complete its challenge at `/auth/login/complete` with a recovery
code or a configured provider's proof; API subscription and role restrictions
continue to apply.

Sensitive actions, including passkey removal and optional personal-token
creation, accept a short-lived, one-use reauthentication proof. Passkey approval
binds this proof to the account, current browser JWT session and exact action.
A proof for token creation cannot remove a passkey, and a proof cannot be reused.
The integration works when the personal-token feature is installed; it is not a
dependency of passkeys.

## Policy, removal and recovery

Account security supports optional MFA, required MFA for privileged local users,
or required MFA for all local users, with an enrollment grace period. After the
grace period, unenrolled users receive only the enrollment workflow. OIDC and
LDAP users continue to use their provider's policy. A policy requiring a factor
prevents removal of the last local factor. When MFA is optional, removing the
last factor requires complete current authentication and removes recovery codes.
Enrollment, removal and recovery invalidate prior sessions and any installed PAT
provider's older security generation.

An operator with root access to the Roxy-WI host can recover a lost local factor:

```sh
python3 local_auth_recovery.py admin --confirm-user admin --reason lost-device
```

The command must run from the installed application environment as root. It
requires the exact account confirmation and a reason (`lost-device`,
`compromise` or `restore`), removes installed local factors and recovery codes,
and advances the account's security generation. It creates a durable local
authentication event even when the external audit destination is unavailable.
Sign in with the local password and enroll again. The command does not change
provider-managed credentials.

## Verification and persistence

Registration and authentication use the maintained Python WebAuthn SDK. The
server verifies the challenge, ceremony type, configured origin, RP ID hash,
credential/account binding, signature, user presence and required user
verification. A returned user handle must match the registered random account
handle. Challenges expire after 120 seconds, are purpose- and session-bound,
and share transactional consumption with credential updates. Replayed,
expired, cross-account, old-password and old-security-generation proofs fail.
Concurrent use of one assertion can succeed only once. Sessions also bind a random
account incarnation, so deleting and recreating a numeric user ID cannot revive
the former account's JWTs. Legacy-session eligibility is initialized once at
migration/bootstrap and is never assigned lazily to a replacement account.
Verified passwords and identity-provider bindings capture one account snapshot;
proof completion and session actors revalidate it under a parent-account lock.
The snapshot includes the incarnation, generation and password change marker,
so an earlier approval cannot bind a replacement account. Locks cover short
database operations; password and external-provider verification run outside them.
Session validation uses a coherent read-only database snapshot and never creates
missing security or policy state; mutation and proof issuance recheck the original
principal under the parent-account lock.

Zero signature counters are valid for authenticators, including synced passkeys.
When either stored or returned counter is nonzero, the SDK requires an increment;
a conditional database update also rejects stale concurrent counter updates.
This is a clone/regression signal, not a claim that every synced authenticator
provides a globally increasing hardware counter. No attestation trust service or
external authentication network call is required.

Back up the database, Flask/JWT signing keys and managed Fernet key together.
Pending challenge payloads are encrypted and included in the existing credential
key rotation command. Public keys and account handles remain in the database.
Deleting an account cascades its credentials and challenge/recovery state.
Restoring an older database may restore formerly valid credentials or recovery
codes: keep the instance inaccessible while resetting security generations,
reviewing factors and revoking restored access.

Credential-version claims use a domain-separated HMAC keyed by the stable Flask
application key, rather than exposing a public digest of a stored password hash.
Rotating the Fernet encryption key does not change this verification fingerprint.
Credential-version claims preserve the existing HMAC-SHA256 values. Legacy MD5
verification remains the existing master implementation; successful password
login upgrades the exact original credential to scrypt using compare-and-set.
Regression fixtures use fixed legacy database records, never newly stored MD5
passwords.

The migrations are additive and idempotent. They deliberately refuse an automatic
down migration. After enabling MFA, do not run an older Roxy-WI version that does
not enforce these tables. A rollback requires an offline maintenance window and
an explicit decision about access policy; deleting factor tables is not a safe
rollback.

## Automated coverage and limits

Product tests use real WebAuthn signatures and the normal product database/routes.
The browser suite uses real Chromium WebAuthn calls with a CDP virtual CTAP2
resident authenticator and user verification. It covers enrollment, passwordless
login, password plus passkey, removal and synthetic light/dark screenshots.
These tests do not qualify physical security keys, biometric devices, mobile
handoff or particular passkey sync providers. Linux VM and database qualification
must be reported separately for the exact published revision.

See [synthetic screenshots](screenshots/local-passkeys/README.md),
[WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/) and the
[Python WebAuthn project](https://github.com/duo-labs/py_webauthn).

When external audit export is installed, only completed, verified login events
may use its bounded repair reserve if the normal queue is full. Configuration
changes and denied or unverified attempts cannot consume that reserve. Exhausting
the reserve fails the login without issuing a session; local denial accounting
and the failure gate remain durable when external export is unavailable.
