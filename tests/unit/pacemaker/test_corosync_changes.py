"""Exercise reviewed membership changes against a real test database and fake SSH."""
import itertools
import json
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import PacemakerChange, PacemakerEvent, Server
from app.modules.pacemaker import corosync, qdevice, service, witness_migration
from app.modules.pacemaker.schemas import ClusterCreate, CorosyncCandidate, Member
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiInputError, RoxywiValidationError


@pytest.fixture
def topology(monkeypatch):
    servers = [Server.create(hostname=f'membership-node-{i}', ip=f'192.0.2.{180+i}', group_id=1)
               for i in range(1, 6)]
    members = [Member(server_id=s.server_id, name=s.hostname, address=s.ip, nodeid=i)
               for i, s in enumerate(servers[:4], 1)]
    cluster = service.register(ClusterCreate(name='membership-test', members=members[:2]), 1)
    calls = []
    witness = servers[-1]
    state = SimpleNamespace(votes={}, tls={}, hosts={}, initialized=[])

    class Remote:
        def __init__(self, server):
            self.server = server

        def run(self, args, **kwargs):
            calls.append((self.server.server_id, args, kwargs))
            if args == ['cat', '/etc/corosync/corosync.conf']:
                return 'original corosync configuration'
            if args[:1] == ['hostname']:
                return self.server.hostname
            if args == ['python3', '-c', corosync.PREPARE]:
                return json.dumps({'fence_pve_repaired': False})
            if args == ['env', 'LC_ALL=C', 'corosync-quorumtool', '-s']:
                return f'Quorate: Yes\nFlags: Quorate Qdevice\n0 {state.votes.get(self.server.server_id, 1)} Qdevice\n'
            if args == ['env', 'LC_ALL=C', 'corosync-qdevice-tool', '-s', '-v']:
                return (f'QNetd host: {state.hosts.get(self.server.server_id, witness.ip)}:5403\n'
                        f'TLS active: {state.tls.get(self.server.server_id, "Yes")}\n')
            return ''

    monkeypatch.setattr(corosync, 'Remote', Remote)
    monkeypatch.setattr(witness_migration, 'Remote', Remote)
    monkeypatch.setattr(service, 'status', lambda row: {
        'quorate': True, 'resources': [],
        'nodes': [{'name': m.name, 'online': 'true', 'standby': 'true', 'unclean': 'false'}
                  for m, _s in service.members(row)],
    })
    monkeypatch.setattr(qdevice, 'initialize', lambda *_args: state.initialized.append(True))
    monkeypatch.setattr(qdevice, 'extend', lambda *_args: None)
    # Exercise the real readiness/retry logic without a 75-second failure delay.
    clock = itertools.count(step=76)
    monkeypatch.setattr(witness_migration, 'time', SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None))
    yield SimpleNamespace(cluster=cluster, members=members, servers=servers, witness=witness, calls=calls, state=state)
    cluster.delete_instance(recursive=True)
    for server in servers:
        server.delete_instance()


def make_change(topology, members=None, *, witness=False):
    return corosync.draft(topology.cluster, 1, CorosyncCandidate(
        name=topology.cluster.name, members=members if members is not None else topology.members[:2],
        qdevice_server_id=topology.witness.server_id if witness else None,
    ))


@pytest.mark.parametrize('apply', [False, True], ids=['validate', 'apply-previously-validated'])
def test_full_membership_replacement_is_rejected_before_remote_changes(topology, apply):
    change = make_change(topology, topology.members[2:])
    if apply:
        # A draft validated by an older version must still be refused at apply time.
        change.status = 'validated'
        change.save()
    topology.calls.clear()
    with pytest.raises(RoxywiInputError, match='at least one existing member'):
        corosync.execute(topology.cluster, change, 1, apply=apply)
    assert all(args == ['cat', '/etc/corosync/corosync.conf'] for _s, args, _kw in topology.calls)
    assert json.loads(service.get_cluster(topology.cluster.id, 1).servers) == [m.model_dump() for m in topology.members[:2]]
    assert PacemakerChange.get_by_id(change.id).status == ('validated' if apply else 'draft')


def test_apply_rechecks_current_membership_after_validation(topology):
    change = make_change(topology)
    corosync.execute(topology.cluster, change, 1)
    assert PacemakerChange.get_by_id(change.id).status == 'validated'
    # Another reviewed change can have replaced the registered topology since validation.
    topology.cluster.servers = json.dumps([m.model_dump() for m in topology.members[2:]])
    topology.cluster.save()
    topology.calls.clear()
    with pytest.raises(RoxywiInputError, match='at least one existing member'):
        corosync.execute(service.get_cluster(topology.cluster.id, 1), change, 1, apply=True)
    assert all(args == ['cat', '/etc/corosync/corosync.conf'] for _s, args, _kw in topology.calls)


def test_partial_membership_replacement_retains_a_reload_node(topology):
    change = make_change(topology, [topology.members[0], topology.members[2]])
    corosync.execute(topology.cluster, change, 1)
    corosync.execute(topology.cluster, change, 1, apply=True)
    assert PacemakerChange.get_by_id(change.id).status == 'applied'
    assert (topology.servers[0].server_id, ['corosync-cfgtool', '-R'], {}) in topology.calls
    assert (topology.servers[2].server_id, ['systemctl', 'enable', '--now', 'corosync', 'pacemaker'], {'timeout': 90}) in topology.calls


@pytest.mark.parametrize('member_index', [0, 1], ids=['first-member', 'last-member'])
@pytest.mark.parametrize('fault', ['zero-votes', 'no-tls', 'wrong-witness'])
def test_witness_attachment_cannot_succeed_without_every_tls_vote(topology, member_index, fault):
    server_id = topology.servers[member_index].server_id
    if fault == 'zero-votes':
        topology.state.votes[server_id] = 0
    elif fault == 'no-tls':
        topology.state.tls[server_id] = 'No'
    else:
        topology.state.hosts[server_id] = '192.0.2.254'
    change = make_change(topology, witness=True)
    corosync.execute(topology.cluster, change, 1)
    with pytest.raises(RoxywiValidationError, match='TLS witness vote|another witness'):
        corosync.execute(topology.cluster, change, 1, apply=True)
    assert topology.state.initialized == [True]
    assert PacemakerChange.get_by_id(change.id).status == 'unknown'
    assert not PacemakerEvent.select().where(
        (PacemakerEvent.cluster == topology.cluster.id) & (PacemakerEvent.status == 'applied')).exists()
    before = list(topology.calls)
    with pytest.raises(RoxywiConflictError, match='already attempted'):
        corosync.execute(topology.cluster, change, 1, apply=True)
    assert topology.calls == before


@pytest.mark.parametrize('replace_member', [False, True], ids=['current-members', 'new-member'])
def test_witness_attachment_checks_all_members_before_reporting_applied(topology, replace_member):
    members = [topology.members[0], topology.members[2 if replace_member else 1]]
    change = make_change(topology, members, witness=True)
    corosync.execute(topology.cluster, change, 1)
    corosync.execute(topology.cluster, change, 1, apply=True)
    assert PacemakerChange.get_by_id(change.id).status == 'applied'
    verified = {server_id for server_id, args, _kw in topology.calls
                if args == ['env', 'LC_ALL=C', 'corosync-qdevice-tool', '-s', '-v']}
    assert verified == {member.server_id for member in members}


def test_witness_attachment_waits_for_a_transiently_missing_vote(topology, monkeypatch):
    first_id = topology.servers[0].server_id
    topology.state.votes[first_id] = 0
    original = witness_migration.verify
    attempts = []

    def verify(clusters, witness_ip):
        attempts.append(True)
        try:
            original(clusters, witness_ip)
        except RoxywiValidationError:
            topology.state.votes[first_id] = 1
            raise

    monkeypatch.setattr(witness_migration, 'verify', verify)
    clock = itertools.count()
    monkeypatch.setattr(witness_migration, 'time', SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None))
    change = make_change(topology, witness=True)
    corosync.execute(topology.cluster, change, 1)
    corosync.execute(topology.cluster, change, 1, apply=True)
    assert len(attempts) == 2
    assert PacemakerChange.get_by_id(change.id).status == 'applied'
