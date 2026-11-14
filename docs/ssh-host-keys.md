# Confirm SSH server identities

When adding a physical server, Roxy-WI reads its public SSH host key and opens a
confirmation dialog showing the address, port, key type and SHA-256 fingerprint.
No SSH credentials are sent and no server record is created until you confirm.
Cancel keeps the form available for editing.

Compare the fingerprint through a trusted channel, such as the server console.
For an Ed25519 host key, run on that server:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Use the public host-key file matching the key type shown in the dialog. This is
the server's identity key, not the user's SSH login key.

Roxy-WI rechecks the key when you confirm. If it changed while the dialog was
open, a new confirmation shows both fingerprints. Subsequent SSH connections and
Ansible installations verify the approved key. Approval expires after ten minutes
and cannot be reused by another user or with changed server details.

Virtual IP entries do not perform SSH discovery. Changing an entry to a physical
server, or changing its SSH address or port, requires confirmation before saving.

## Existing servers and key replacement

Previously trusted entries in the application's SSH `known_hosts` file remain
usable. Unknown keys are no longer accepted automatically. In
**Administration → Servers → Actions → Check SSH**, review and confirm the host
key before testing the authenticated connection. The same action supports a
deliberate key replacement after a server reinstall; it shows the previous and
new fingerprints. Only administrators with access to the server can approve it.

Approved public keys are stored with their server registration and included in
database backups. An upgrade does not automatically trust any network keys.
Independent filesystem-backup destinations must have their own trusted entry in
the application's SSH `known_hosts` file; a source server's approval does not
trust a different backup host.

## HTTP API

`POST /api/server` and endpoint-changing `PUT /api/server/ID` return HTTP 409 with
`code: "ssh_host_key_confirmation_required"`, `host_key` details and a signed
`confirmation` value when approval is needed. After verifying the fingerprint,
repeat the same request with `ssh_host_key_confirmation` set to that value.
Automation must make an explicit trust decision; omitting server scanning does
not bypass host-key confirmation.

For an existing server, send an empty JSON object to
`POST /api/server/ID/ssh-host-key`. An unchanged approved key returns HTTP 200.
Otherwise, review the HTTP 409 response and repeat with
`{"ssh_host_key_confirmation": "<confirmation>"}`. An expired or invalid token
must be discarded; repeat the initial request to review a fresh fingerprint.

Browser endpoints use the same checks and additionally require the normal CSRF
token. Confirmation is scoped to the current user, group and server registration.
