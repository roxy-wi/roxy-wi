"""Account and membership boundaries for GHSA-9r6g-8j5v-c6fj."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask_jwt_extended import create_access_token

from app.modules.db import user as user_sql
from app.modules.db.db_model import Groups, User, UserGroups
from app.modules.roxy_wi_tools import Tools
from app.modules.roxywi import common


pytestmark = [pytest.mark.security, pytest.mark.rbac]
NEW_PASSWORD = 'Regression-new-password-123!'


@pytest.fixture
def accounts(app, monkeypatch):
    """Use real users, memberships and JWT authorization, isolated per test."""
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {
        'user_status': 1, 'user_plan': 'business',
    })
    suffix = uuid4().hex
    own = Groups.create(name=f'own-{suffix}', description='test')
    other = Groups.create(name=f'other-{suffix}', description='test')
    users = []
    password_hash = Tools.get_hash('Regression-original-password-123!')

    def create(role=3, *, memberships=None, active=None, legacy=None):
        memberships = {own.group_id: role} if memberships is None else memberships
        name = f'account-{suffix}-{len(users)}'
        user = User.create(
            username=name, email=f'{name}@example.test', password=password_hash,
            role_id=str(role if legacy is None else legacy),
            group_id=str(own.group_id if active is None else active), enabled=1,
        )
        users.append(user.user_id)
        for group_id, member_role in memberships.items():
            user_sql.update_user_role(user.user_id, group_id, member_role)
        return user

    def headers(user):
        with app.app_context():
            token = create_access_token(str(user.user_id), additional_claims={'group': user.group_id})
        return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    actor = create(2)
    try:
        yield SimpleNamespace(own=own.group_id, other=other.group_id, create=create,
                              actor=actor, headers=headers)
    finally:
        UserGroups.delete().where(UserGroups.user_id.in_(users)).execute()
        User.delete().where(User.user_id.in_(users)).execute()
        Groups.delete().where(Groups.group_id.in_([own.group_id, other.group_id])).execute()


def snapshot(user):
    stored = User.get_by_id(user.user_id)
    memberships = sorted((row.user_group_id, row.user_role_id) for row in
                         UserGroups.select().where(UserGroups.user_id == user.user_id))
    return dict(stored.__data__), memberships


def update_body(user):
    return {'username': user.username, 'email': user.email, 'enabled': 1, 'password': NEW_PASSWORD}


@pytest.mark.parametrize('prefix', ['', '/api'])
@pytest.mark.parametrize('method', ['POST', 'PUT'])
def test_group_admin_cannot_demote_then_take_over_superadmin(client, accounts, prefix, method):
    target = accounts.create(1, memberships={accounts.own: 1, accounts.other: 1}, active=accounts.other)
    before = snapshot(target)
    headers = accounts.headers(accounts.actor)
    demote = client.open(f'{prefix}/user/{target.user_id}/groups/{accounts.own}',
                         method=method, headers=headers, json={'role_id': 4})
    reset = client.put(f'{prefix}/user/{target.user_id}', headers=headers, json=update_body(target))
    assert demote.status_code in (403, 404), demote.get_data(as_text=True)
    assert reset.status_code in (403, 404), reset.get_data(as_text=True)
    assert snapshot(target) == before
    assert not Tools.check_password(NEW_PASSWORD, User.get_by_id(target.user_id).password)[0]


@pytest.mark.parametrize('privilege', ['foreign', 'legacy', 'orphan'])
@pytest.mark.parametrize('method', ['POST', 'PUT', 'DELETE'])
def test_membership_changes_protect_superadmin_in_every_role_representation(
        client, accounts, privilege, method):
    target = accounts.create(4, legacy=1 if privilege == 'legacy' else 4)
    if privilege != 'legacy':
        group_id = accounts.other if privilege == 'foreign' else accounts.other + 100000
        user_sql.update_user_role(target.user_id, group_id, 1)
    before = snapshot(target)
    response = client.open(f'/user/{target.user_id}/groups/{accounts.own}', method=method,
                           headers=accounts.headers(accounts.actor), json={'role_id': 4})
    assert response.status_code in (403, 404), response.get_data(as_text=True)
    assert snapshot(target) == before


@pytest.mark.parametrize('prefix', ['', '/api'])
@pytest.mark.parametrize('foreign_role', [1, 2, 3, 4])
@pytest.mark.parametrize('operation', ['update', 'delete'])
def test_group_admin_cannot_change_global_account_shared_with_another_group(
        client, accounts, prefix, foreign_role, operation):
    target = accounts.create(4, memberships={accounts.own: 4, accounts.other: foreign_role},
                             active=accounts.own)
    before = snapshot(target)
    response = client.open(f'{prefix}/user/{target.user_id}',
                           method='PUT' if operation == 'update' else 'DELETE',
                           headers=accounts.headers(accounts.actor), json=update_body(target))
    assert response.status_code in (403, 404), response.get_data(as_text=True)
    assert snapshot(target) == before


def test_adding_foreign_admin_to_own_group_does_not_allow_password_reset(client, accounts):
    target = accounts.create(2, memberships={accounts.other: 2}, active=accounts.other)
    headers = accounts.headers(accounts.actor)
    added = client.post(f'/user/{target.user_id}/groups/{accounts.own}',
                        headers=headers, json={'role_id': 4})
    assert added.status_code == 201
    before = snapshot(target)
    reset = client.put(f'/user/{target.user_id}', headers=headers, json=update_body(target))
    assert reset.status_code in (403, 404)
    assert snapshot(target) == before


@pytest.mark.parametrize('foreign_role', [1, 2, 4])
def test_shared_account_service_permissions_cannot_be_rewritten(client, accounts, foreign_role):
    target = accounts.create(4, memberships={accounts.own: 4, accounts.other: foreign_role})
    before = snapshot(target)
    response = client.post(f'/user/services/{target.user_id}', headers=accounts.headers(accounts.actor),
                           json={'username': target.username, 'services': {'selected': {'1': True}}})
    assert response.status_code == 403
    assert snapshot(target) == before


@pytest.mark.parametrize('role', [2, 3, 4])
@pytest.mark.parametrize('prefix', ['', '/api'])
def test_group_admin_can_still_manage_local_peer_and_lower_accounts(client, accounts, role, prefix):
    target = accounts.create(role)
    headers = accounts.headers(accounts.actor)
    for method in ('POST', 'PUT', 'PUT'):
        response = client.open(f'{prefix}/user/{target.user_id}/groups/{accounts.own}',
                               method=method, headers=headers, json={'role_id': role})
        assert response.status_code == 201, response.get_data(as_text=True)
    response = client.put(f'{prefix}/user/{target.user_id}', headers=headers, json=update_body(target))
    assert response.status_code == 201, response.get_data(as_text=True)
    assert Tools.check_password(NEW_PASSWORD, User.get_by_id(target.user_id).password)[0]
    response = client.delete(f'{prefix}/user/{target.user_id}', headers=headers)
    assert response.status_code == 204, response.get_data(as_text=True)
    assert not User.select().where(User.user_id == target.user_id).exists()


def test_superadmin_can_manage_user_without_membership_in_active_group(client, accounts):
    actor = accounts.create(1)
    target = accounts.create(2, memberships={accounts.other: 2}, active=accounts.other)
    response = client.put(f'/user/{target.user_id}', headers=accounts.headers(actor), json=update_body(target))
    assert response.status_code == 201, response.get_data(as_text=True)
    assert Tools.check_password(NEW_PASSWORD, User.get_by_id(target.user_id).password)[0]


@pytest.mark.parametrize('foreign_role', [1, 2])
@pytest.mark.parametrize('legacy_role', [1, 2])
def test_group_admin_can_edit_own_profile_and_password_when_in_multiple_groups(
        client, accounts, foreign_role, legacy_role):
    user_sql.update_user_role(accounts.actor.user_id, accounts.other, foreign_role)
    User.update(role_id=str(legacy_role)).where(User.user_id == accounts.actor.user_id).execute()
    headers = accounts.headers(accounts.actor)
    response = client.put(f'/user/{accounts.actor.user_id}', headers=headers, json=update_body(accounts.actor))
    assert response.status_code == 201, response.get_data(as_text=True)
    response = client.post('/user/password', headers=headers, json={'pass': NEW_PASSWORD})
    assert response.status_code == 200


@pytest.mark.parametrize('role', [3, 4])
def test_nonadmin_can_still_read_own_service_permissions(client, accounts, role):
    actor = accounts.create(role)
    response = client.get(f'/user/services/{actor.user_id}', headers=accounts.headers(actor))
    assert response.status_code == 200
