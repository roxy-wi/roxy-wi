# Certificate deployment verification

After an HAProxy certificate update has committed on all selected nodes, Roxy-WI
makes a **one-time observation of the certificate actually served**. This applies
to manual Runtime API updates, deployment from an external certificate source
such as CertWarden, and successful Let's Encrypt issuance or renewal.

The expected SHA-256 leaf fingerprint and certificate names come from the exact
validated bundle deployed by that operation. The check compares the leaf returned
by selected proxy listeners with that fingerprint and with the other nodes. It
uses concrete certificate names as SNI, or matching configured names for wildcard
certificates. Only TLS binds discovered in the proxy configuration are checked,
in the saved Docker/Podman network namespace when applicable. It sends no HTTP
requests, credentials or private keys, and does not follow DNS destinations.

Open the existing **Certificates → History** dialog to expand **Deployment
verification**. External certificate sources also display the result in their
existing status row; Let's Encrypt shows it in its status and operation history.
Evidence is timestamped and stored with the owning operation. Reading history
does not contact a proxy or repeat a check.

- **Expected certificate served** means every inspected selected listener returned
  the expected leaf and its discovered configuration sources and runtime binding remained
  unchanged during verification.
- **Certificate mismatch** identifies a different served leaf on at least one
  listener. The expected and actual SHA-256 fingerprints are shown per endpoint.
- **Verification incomplete** identifies unreachable listeners, failed TLS
  handshakes, changed configuration, an unavailable target, a configuration whose
  running sources cannot be confirmed, or discovery/probe limits.

Certificate delivery and listener verification have separate results. A mismatch
or unreachable listener does not roll back an already committed deployment or
claim the certificate was not written. Passive Pacemaker nodes remain stopped:
their disk staging is reported as incomplete live verification, without starting
or relocating a service. Failed deployments and rollbacks do not start a check.
An unchanged provider synchronization that does not deploy anything also does
not schedule a new listener check.

The operation checks at most 32 nodes, 100 certificate names and 32 listener/SNI combinations. Additional
scope is explicitly incomplete. Wildcard-only certificates require a concrete
matching name in the discovered configuration; arbitrary names are not invented.
Non-TLS binds and hostnames unrelated to the certificate are excluded. Missing
observations never establish peer agreement.

This verifies delivery of a pinned leaf certificate. System CA trust is retained
as a separate observation and is not the deployment identity criterion; this
allows private PKI to be identified without configuring a monitor trust store.
There is no standalone TLS monitor, recurring TLS-check scheduler, certificate
expiry threshold, monitor-management screen or notification policy in this PR.
Ongoing HTTPS/TLS, expiry and availability monitoring belongs in RMON through the
planned Roxy-WI integration; that integration is outside this change.
