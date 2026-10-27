# Reproducing Corosync/Pacemaker verification

The ordinary suite uses isolated application data and mocks SSH; it does not
contact or change clusters. Run it using the development environment from
[CONTRIBUTING](../CONTRIBUTING.md):

```sh
python -m pytest -q
```

`tests/unit/pacemaker` covers registration/adoption, role/group isolation, native
package profiles, CIB editing/validation, durable jobs, metadata/discovery,
quorum/witness handling, migration recovery, exporter, daemon recovery policies
and transport maintenance. Host programs are also compiled and exercised with
controlled command/filesystem doubles. This is not qualification of every
third-party agent or application deployment.

`test_corosync_changes.py` uses the test database and mocked SSH to reproduce full
membership replacement, stale validation and an otherwise quorate cluster with a
missing witness vote. It also checks TLS/address failures on each member, a
successful partial replacement, verification of new members and delayed vote readiness.

## Existing read-mostly cluster integration tests

`tests/integration/test_pacemaker_live.py` exercises adoption preservation,
existing-installation refusal and a unique Dummy resource transaction/cleanup.
Enable `ROXYWI_PACEMAKER_LIVE=1` and supply the private
`ROXYWI_PACEMAKER_LIVE_CONFIG` described in its module documentation. Every cluster
and node must use the dedicated `roxy-lab` naming convention.

## Mutating HTTP workflow qualification

`tests/integration/test_pacemaker_workflows_live.py` drives the real authenticated
HTTP/CSRF API and Operations worker. It installs exporters, applies/restores daemon
policies, rebuilds the Docker witness, converts Docker → native → Docker, rotates
CAs, moves a witness to an empty target and back, and performs planned transport
maintenance with explicit resource resume.

Use disposable, already registered lab clusters, working SSH/sudo, healthy quorum,
configured fencing, an attached TLS witness, and a separate empty witness target.
These tests intentionally stop application resources and cluster daemons and
change client certificates. Do not point them at production. They reject a public
controller address, require explicit disposable-lab confirmation and verify the
`roxy-lab` prefix on every selected cluster/node/witness before mutation.

Create a private JSON file (mode 0600), for example:

```json
{
  "base_url": "http://127.0.0.1:8080",
  "username": "lab-operator",
  "password": "replace-with-private-lab-password",
  "confirmation": "disposable-roxy-lab",
  "clusters": [1, 2],
  "exporter_nodes": [1, 5],
  "docker_witness": 3,
  "rotate_witnesses": [3, 7],
  "witness_move": {"source": 3, "target": 4},
  "transport_cluster": 2
}
```

IDs are examples, not a required topology. Read the actual registered IDs from the
lab API. `exporter_nodes` contains server IDs of checked cluster members;
witness IDs must refer to separate checked lab servers. Omit optional workflow
entries to skip them. The proxy/controller needs normal access to the private
endpoint. HTTPS certificate verification remains enabled; an optional `ca_bundle`
path can supply a private test CA. The HTTP example is for a local isolated lab.

```sh
chmod 600 /private/path/workflows.json
ROXYWI_PACEMAKER_WORKFLOWS_LIVE=1 \
ROXYWI_PACEMAKER_WORKFLOWS_CONFIG=/private/path/workflows.json \
python -m pytest -q tests/integration/test_pacemaker_workflows_live.py
```

The tests wait for terminal Operations results and inspect actual service state,
CA identities, quorum/votes, configuration digests and resumed resources.
Unconfigured workflows are skipped. Normal CI skips the entire module.
A witness move leaves the spare target stopped after returning to the original
source. CA rotation deliberately retains the new CA; image refresh retains the
new image. Restart policies and prior node availability are restored.

If an operation reports an unknown outcome or loses connectivity, inspect its
GUI journal/recovery before retrying; do not force quorum or replay a failed job.
The tests do not shut down VMs, create hypervisor permissions, enable paid package
repositories or discover credentials. Real fencing/power-loss qualification needs
an explicitly isolated hypervisor/device test setup and is recorded separately.

See the [verification record](corosync-pacemaker-verification.md) for concrete
Debian/Rocky versions, executed scenarios, skipped environments and limits.
