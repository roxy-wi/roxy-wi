# External audit export

Administrators can configure **Admin area → External audit** to export selected
security and change events. The feature is off until a receiver is enabled. It
uses the existing database and Scheduler role; no extra container or package is
required. Keep Scheduler running in container and package deployments.

## Receivers and credentials

The default is RFC 5424 syslog over **TCP + TLS**, port 6514, TLS 1.2 or newer,
with hostname and certificate validation. A custom CA and client certificate/key
can be supplied for mutual TLS. Administrators can explicitly select plain TCP
or UDP, normally port 514. Those transports expose audit contents on the network;
there is no automatic fallback from TLS to an unencrypted transport.

TCP supports RFC 6587 octet counting (default) or newline framing. UDP sends one
RFC 5424 message per datagram and rejects messages exceeding 8192 bytes. Severity
is warning for denied/failed/unknown outcomes and informational otherwise;
facility is authpriv, APP-NAME `roxy-wi`, MSGID `audit`.

An HTTPS JSON receiver can instead authenticate with Basic, Bearer or a named API
key header, plus optional mutual TLS. Standard TCP/UDP syslog has no generic
username/password exchange. URLs cannot contain credentials, query parameters or
fragments. Redirects are never followed and receiver response bodies are neither
stored nor displayed. Configure the receiver to return a 2xx status after
acceptance. The test button sends a HEAD request for HTTPS, or connects and closes
TCP/TLS without an audit message. UDP has no connection test.

Receiver secrets and every immutable historical receiver revision use the
existing Fernet credential key, including `rotate_credential_secret.py`. Values
are never returned to the browser; empty fields preserve saved values and Clear
removes them. Take the normal protected database/key backup before key rotation.
No container engine socket or host-wide privileges are needed.

This PR works independently of shared connection profiles. When that feature is
also installed, a receiver can select a group-visible profile. Saving pins its
current revision; re-save the receiver to adopt a later profile revision.
Deactivating a profile blocks its pinned deliveries. Referenced profiles cannot
be deleted until pinned work and retained receiver revisions have been pruned.
Switching a shared profile to inline settings never copies its hidden credentials
into the new editable endpoint.
Changing an inline receiver's transport, host, port, full URL or authentication
identity requires explicitly replacing or clearing every retained password,
token and client certificate/key. Renaming or changing timeout/framing preserves
credentials for the same identity; an existing CA may also be retained.

Super administrators manage any scope, including group 0 (all groups). Group
administrators manage their current group only. Operators cannot manage receivers
or inspect delivery state. Each receiver accepts `*` or a list of exact event
types. At most 20 receivers may exist per instance. Disable a receiver through
Edit to stop selecting it for future events. Already queued work retains its
pinned endpoint; disabling a receiver does not discard that work.

A group-scoped receiver also holds a restrictive database reference to its group,
so deleting and recreating a numeric group ID cannot transfer the former tenant's
receiver or hidden credentials. A database check also prevents an inconsistent
numeric scope/ownership pointer. A refused group deletion preserves its OIDC
mappings, memberships and settings in the same transaction. Shared scope `0`
uses no group row. To retire a receiver, disable it and finish every delivery
first, then choose **Delete**.
Deletion refuses pending, sending or failed work. It removes only terminal
delivery rows, receiver revisions and their shared-profile use references;
the audit event history remains. If the shared profile adapter was removed,
restore it before cleaning up receiver revisions that reference it.

## Event schema and guarantees

Version 1 JSON includes an event UUID, UTC timestamp, event type/outcome, actor ID
and server-resolved username, group, source IP when available, and typed details.
Only an explicit detail allowlist is exported. Request bodies, passwords, tokens,
private keys, configuration contents, command output and exception text are not
copied into events. Configuration snapshots can be represented by SHA-256 digests
when the managed Change Center snapshot is available. On failed/ongoing events,
these hashes describe the saved before/candidate snapshots, not a verified remote
after-state. Successful rollback events reverse the snapshot roles. Events are
not a substitute for configuration history.

Implemented sources:

- `auth.login`: local web/API login result, with pending distinct from completed.
- `request.started` / `request.finished`: authenticated HTTP mutations, correlated
  by request ID and route template. A successful response means accepted by HTTP,
  **not** successful completion of a queued operation. GET actions and requests
  rejected by earlier authentication guards do not produce these intent records.
- `operation.started` / `operation.finished`: Operations worker execution and its
  actual persisted completed/failed/unknown result.
- Change Center timeline events preserve an existing `change.` prefix, such as
  `change.validated`; other timeline namespaces receive one, such as
  `change.deployment.succeeded` or `change.target.deployed`. These include approvals,
  validation, deployment and rollback, excluding raw timeline details/output.
- `audit.receiver.saved`, `audit.receiver.deleted`, `audit.receiver.check_requested`, `audit.receiver.checked`,
  `audit.delivery.retry_requested`: audit administration itself. A changed or
  disabled receiver also receives its configuration event through its old revision.
  A connection check has a durable intent before opening a socket; failed intent
  storage prevents the check, while failed result storage explicitly reports that
  the check may have executed.
  Receiver deletion is recorded transactionally to other matching enabled
  receivers or local history; it never creates new pending work for the deleted
  receiver. An audit storage failure rolls the deletion back.

Each event and its outbound delivery rows are written atomically. Business
mutations are **not** atomically committed with audit results: a durable intent
precedes a normal HTTP mutation, and a separate result follows it. If storage
fails before intent, the mutation is refused with 503. If result recording fails
after execution, the response explicitly says the action may have completed;
it does not claim a rollback. Change Center retains its existing internal timeline
if exporting a result fails. Monitor application error logs as well as the queue.
Unknown operation results remain unknown rather than being reported successful.

The local store is bounded to 10,000 retained events by default. Set
`ROXYWI_AUDIT_MAX_EVENTS` to a value between 100 and 100,000 if needed. A further
100 slots are reserved for already-started action results, successful/pending
sign-in and audited receiver repair. If that reserve is exhausted, result recording can also fail. Exported
records remain locally for 30 days; Scheduler removes up to 200 expired records
per run **only after all their deliveries reach a terminal transport state**.
Pending, failed and in-flight work is never removed by retention. Check disk space
and configure capacity for the retention period; delivery does not immediately
free event quota. With any receiver enabled, HTTP audit intent applies instance
wide, even to a group without its own receiver. Group 0 receivers receive all
groups, including unauthenticated login failures without a group identity.

Scheduler claims deliveries with a five-minute lease and sends bounded batches
outside database transactions. Transient errors use exponential retry with jitter
(up to five minutes); permanent HTTP 4xx responses except 408/429 become Failed.
Certificate verification failure becomes Failed for explicit trust repair;
transient TLS EOF, network and timeout errors remain retryable. Connection errors
are sanitized. An expired worker lease can be reclaimed after
a process restart. An old worker cannot overwrite a newer claim's result.
The delivery deadline is 1–10 seconds, including writes and response headers once
the socket opens. A receiver trickling HTTP headers cannot indefinitely retain a
Scheduler call. Connection attempts and TLS setup consume the same delivery
budget; if setup exhausts it, no payload is sent. DNS resolution follows the host
resolver's timeout. A single receiver may therefore extend the scheduler batch's
nominal time budget while its current call finishes.

Delivery is **at least once under recovery**, not exactly once: the receiver may
have accepted a message immediately before a sender crash. Receivers should
deduplicate by the JSON UUID. **Requeue undelivered** explicitly rebinds pending
and failed work to the **current receiver revision**, preserving that UUID. Its
confirmation warns that delivery can be duplicated. Sending and terminal work
is never rebound; duplicate work already queued or in flight for the current
revision is preserved. This can repair a former endpoint or credential failure
without silently changing already queued deliveries during an ordinary edit.

The GUI distinguishes:

- Waiting / Sending / Failed.
- Handed to TCP/TLS transport: the write completed, no archival acknowledgement.
- Accepted by HTTPS receiver: a 2xx reply, no guarantee of downstream archival.
- UDP datagram sent: no receipt or delivery acknowledgement.

This is an operational audit export, not a tamper-proof database or a delivery
SLA. A database/host administrator can alter local records. Protect the external
collector independently, restrict receiver administration, and monitor failed or
stalled export. There is no generic syslog login or encrypted UDP mode.

## HTTP administration and diagnostics

All endpoints require the existing cookie session, CSRF and administrator checks:
`GET /admin/audit-receivers`, `POST /admin/audit-receivers`,
`PUT /admin/audit-receivers/<id>`, `DELETE /admin/audit-receivers/<id>`, `GET /admin/audit-status`,
`POST /admin/audit-receivers/<id>/test` and
`POST /admin/audit-receivers/<id>/retry`.
Do not attach an Authorization header to these interactive requests: header-only
and mixed cookie/header identities are rejected. Updates and retry require the current `revision`; stale changes return 409.
The retry API defaults to failed rows only. Set `include_pending: true` explicitly
to use the same pending-and-failed repair action as the GUI; this must be a JSON
boolean. Every repair is audited in the same transaction.
DELETE requires JSON `{"revision": <current revision>}`, a disabled receiver and
no undelivered work; stale revisions return 409. Its bounded audit reserve is the
same as other receiver administration and does not erase retained events.
`Cache-Control: no-store` applies to JSON responses. Group administrators cannot
inspect other groups' queue or receiver data. For API creation without profiles:

```json
{
  "name": "Central audit", "group_id": 1, "enabled": true, "events": ["*"],
  "connection": {
    "transport": "tcp_tls", "host": "audit.example.test", "port": 6514,
    "framing": "octet_counting", "auth": "none", "secrets": {}
  }
}
```

If normal quota is full, an administrator can still use the reserved allowance to
repair or disable a receiver, or retry failed work. Restore receiver availability,
inspect quota and disk, and retain/export old events before deleting anything
manually. Rolling back the schema refuses to erase audit history or pending work.

## Verification

Product scenarios exercise scope/role checks, encryption and rotation, immutable
revisions, secret redaction, exact event filters, transaction rollback, concurrent
writers, failed-delivery repair, quota and retention, stale worker recovery,
operation results, safe configuration digests, login and idempotent migration.
Loopback tests use real TCP/TLS/UDP/HTTPS receivers, validate RFC framing and
JSON, Basic/Bearer/API-key headers, redirect isolation and sanitized HTTP errors.
The optional browser scenarios verify the real page and light/dark screenshots.
See [screenshots](screenshots/external-audit/README.md) for their exact scope.
Lab/SELinux and hosted CI results belong in the PR after draft publication; local
checks alone do not establish them.
