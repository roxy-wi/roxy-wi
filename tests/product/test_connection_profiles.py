import json

import pytest

from app.modules.db.db_model import ConnectionProfile, UserGroups
from app.modules.integrations import connection_profiles as profiles
from app.modules.integrations import connection_transport as transport
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound


URL = '/admin/connection-profiles'


def body(**changes):
    return {'name': 'Audit receiver', 'group_id': 1, 'transport': 'https',
            'url': 'https://audit.example.test/events', 'auth': 'basic', 'username': 'sender',
            'secrets': {'password': '  keep this exact password  '}, **changes}


def test_create_edit_and_pin_revision_without_exposing_credentials(product_client, product):
    response = product_client.post(URL, json=body())
    assert response.status_code == 201
    created = response.json
    assert response.headers['Cache-Control'] == 'no-store'
    assert created['configured']['password'] is True
    assert 'keep this' not in response.text
    row = ConnectionProfile.get_by_id(created['id'])
    assert 'keep this' not in row.credentials_encrypted
    first = profiles.resolve(row.id, 1)
    assert first.credentials['password'] == '  keep this exact password  '
    assert 'keep this' not in repr(first)

    changed = product_client.put(f'{URL}/{row.id}', json=body(
        revision=1, name='Updated receiver', secrets={}))
    assert changed.status_code == 200
    assert changed.json['revision'] == 2
    assert profiles.resolve(row.id, 1).credentials == first.credentials
    assert profiles.resolve(row.id, 1, revision=1).settings == first.settings
    assert 'keep this' not in product_client.get(URL).text

    stale = product_client.put(f'{URL}/{row.id}', json=body(revision=1))
    assert stale.status_code == 409
    assert profiles.resolve(row.id, 1).revision == 2


def test_cross_group_visibility_and_operator_authorization(product_client, product):
    other = product_client.post(URL, json=body(group_id=2))
    assert other.status_code == 201
    other_id = other.json['id']
    assert other_id not in [p['id'] for p in product_client.get(URL).json['profiles']]
    with pytest.raises(RoxywiResourceNotFound):
        profiles.resolve(other_id, 1)
    assert product_client.put(f'{URL}/{other_id}', json=body(revision=1)).status_code == 404

    shared = product_client.post(URL, json=body(group_id=0))
    assert shared.status_code == 201
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.post(URL, json=body(group_id=0, name='Forbidden shared')).status_code == 403
    assert product_client.put(f'{URL}/{shared.json["id"]}', json=body(group_id=0, revision=1)).status_code == 403
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(URL).status_code == 403
    assert product_client.post(URL, json=body()).status_code == 403


def test_explicit_secret_removal_and_disabled_profile(product_client, product):
    created = product_client.post(URL, json=body()).json
    endpoint = f'{URL}/{created["id"]}'
    assert product_client.put(endpoint, json=body(revision=1, auth='none', secrets={})).status_code == 400
    updated = product_client.put(endpoint, json=body(
        revision=1, auth='none', secrets={}, clear_secrets=['password'], enabled=False))
    assert updated.status_code == 200
    assert not updated.json['configured']['password']
    with pytest.raises(RoxywiConflictError):
        profiles.resolve(created['id'], 1)
    assert product_client.post(endpoint+'/test', json={}).status_code == 409


def test_reference_prevents_deletion_but_allows_deactivation(product_client, product):
    created = product_client.post(URL, json=body()).json
    profiles.bind_use(created['id'], 1, consumer='audit', consumer_id='destination-1')
    response = product_client.delete(f'{URL}/{created["id"]}', json={'revision': 1})
    assert response.status_code == 409
    assert product_client.put(f'{URL}/{created["id"]}', json=body(
        revision=1, enabled=False, secrets={})).status_code == 200


@pytest.mark.parametrize('changes', [
    {'url': 'https://username:secret@example.test/'}, {'url': 'http://example.test/'},
    {'url': 'https://example.test/?api_key=secret'}, {'url': 'https://example.test/#secret'},
    {'header_name': 'Authorization'}, {'header_name': 'X-Key\r\nInjected'},
    {'secrets': {'token': 'secret\r\nInjected'}}, {'transport': 'tcp', 'host': 'example.test'},
    {'secrets': {'password': 'private', 'unknown': 'secret'}}, {'name': ' '},
])
def test_invalid_input_never_echoes_secret_values(product_client, product, changes):
    response = product_client.post(URL, json=body(**changes))
    assert response.status_code == 400
    assert 'secret' not in response.text.lower()
    assert 'private' not in response.text.lower()
    assert ConnectionProfile.select().count() == 0


@pytest.mark.parametrize('locale', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_profile_page_and_test_result_are_safe(product_client, product, monkeypatch, locale):
    product_client.set_cookie('lang', locale)
    assert product_client.get('/admin/connections').status_code == 200
    created = product_client.post(URL, json=body()).json
    seen = []
    monkeypatch.setattr('app.routes.admin.connection_profiles.check_connection',
                        lambda value: seen.append(value) or {'status': 'connected'})
    response = product_client.post(f'{URL}/{created["id"]}/test', json={})
    assert response.status_code == 200
    assert response.json == {'status': 'connected'}
    assert seen[0].credentials['password'] == '  keep this exact password  '
    assert 'keep this' not in response.text


def test_udp_check_does_not_claim_delivery_or_send_an_unrequested_datagram(product_client, product, monkeypatch):
    response = product_client.post(URL, json=body(
        transport='udp', host='audit.example.test', port=514, auth='none', secrets={}))
    assert response.status_code == 201
    monkeypatch.setattr(transport.socket, 'socket', lambda *a: pytest.fail('UDP connection probe sent data'))
    result = product_client.post(f'{URL}/{response.json["id"]}/test', json={})
    assert result.json['status'] == 'unverified'


def test_metadata_and_mixed_dns_answers_are_rejected_before_connecting(monkeypatch):
    import socket
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
               for ip in ('192.0.2.1', '169.254.169.254')]
    monkeypatch.setattr(transport.socket, 'getaddrinfo', lambda *a, **kw: answers)
    with pytest.raises(ValueError, match='not permitted'):
        transport.destination_addresses('audit.example.test', 443)


def test_profile_history_participates_in_credential_key_rotation(product_client, product, monkeypatch):
    import os
    from cryptography.fernet import Fernet
    from rotate_credential_secret import rotate_credentials

    created = product_client.post(URL, json=body()).json
    old = profiles.resolve(created['id'], 1)
    key = os.environ['ROXYWI_SECRET_PHRASE']
    monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE', key)
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', Fernet.generate_key().decode('ascii'))
    assert rotate_credentials() >= 2
    assert profiles.resolve(created['id'], 1).credentials == old.credentials
    assert profiles.resolve(created['id'], 1, revision=1).credentials == old.credentials
    assert rotate_credentials() == 0


def test_migration_adds_profiles_to_existing_database_without_changing_users(product_client, product):
    import importlib
    from app.modules.db.db_model import ConnectionProfileRevision, ConnectionProfileUse, User

    before = User.select().count()
    product.db.drop_tables([ConnectionProfileUse, ConnectionProfileRevision, ConnectionProfile])
    migration = importlib.import_module('app.modules.db.migrations.20261029010000_connection_profiles')
    migration.up()
    migration.up()
    assert User.select().count() == before
    assert product_client.post(URL, json=body()).status_code == 201


@pytest.mark.parametrize('changes', [
    {'url': 'https://other.example.test/events'}, {'url': 'https://audit.example.test/other-path'},
    {'url': 'https://audit.example.test:9443/events'}, {'username': 'other-sender'},
    {'header_name': 'X-Other-Key'},
])
def test_hidden_credentials_cannot_be_retargeted_without_reentry(product_client, product, changes):
    created = product_client.post(URL, json=body()).json
    result = product_client.put(f'{URL}/{created["id"]}', json=body(revision=1, secrets={}, **changes))
    assert result.status_code == 400 and 'Re-enter or clear' in result.text
    assert 'keep this exact password' not in result.text
    assert profiles.resolve(created['id'], 1).revision == 1
    accepted = product_client.put(f'{URL}/{created["id"]}', json=body(
        revision=1, secrets={'password': 'ReplacementSyntheticPassword!'}, **changes))
    assert accepted.status_code == 200 and accepted.json['revision'] == 2


def test_mtls_identity_cannot_be_redirected_but_can_be_explicitly_cleared(product_client, product):
    from tests.fixtures.certificate_runtime import make_pem
    pem = make_pem(domains=('localhost',))
    certificate, key = pem.split('-----BEGIN PRIVATE KEY-----')
    key = '-----BEGIN PRIVATE KEY-----'+key
    data = body(transport='tcp_tls', host='first.example.test', auth='none', url='',
                secrets=dict(ca_pem=certificate, client_cert_pem=certificate, client_key_pem=key))
    created = product_client.post(URL, json=data)
    assert created.status_code == 201, created.text
    endpoint = f'{URL}/{created.json["id"]}'
    data.update(host='second.example.test', revision=1, secrets={})
    assert product_client.put(endpoint, json=data).status_code == 400
    data['clear_secrets'] = ['client_cert_pem', 'client_key_pem']
    result = product_client.put(endpoint, json=data)
    assert result.status_code == 200
    assert result.json['configured']['ca_pem'] and not result.json['configured']['client_key_pem']


def test_profile_management_requires_cookie_csrf_and_unambiguous_identity(product_client, product, app):
    human = app.test_client().post('/api/login', json=dict(login='admin', password='TestBootstrapPassword!'))
    assert human.status_code == 200
    headers = {'Authorization': 'Bearer '+human.json['access_token'], 'Accept': 'application/json'}
    assert app.test_client().get(URL, headers=headers).status_code == 401
    assert product_client.get(URL, headers=headers).status_code == 403
    product_client.environ_base.pop('HTTP_X_CSRF_TOKEN')
    assert product_client.post(URL, json=body()).status_code == 401
    assert ConnectionProfile.select().count() == 0


def test_shared_profile_metadata_does_not_disclose_other_group_usage(product_client, product):
    shared = product_client.post(URL, json=body(group_id=0)).json
    profiles.bind_use(shared['id'], 2, consumer='synthetic', consumer_id='other-group-usage')
    UserGroups.update(user_role_id=3).where(UserGroups.user_id == product.admin.user_id).execute()
    listed = product_client.get(URL)
    assert listed.status_code == 200
    entry = next(item for item in listed.json['profiles'] if item['id'] == shared['id'])
    assert 'in_use' not in entry
    assert 'other-group-usage' not in listed.text
    assert entry['configured']['password'] is True


def test_group_deletion_cannot_transfer_hidden_profile_to_reused_group_id(product_client, product):
    from peewee import IntegrityError
    from app.modules.db.db_model import Groups
    group = Groups.create(name='Retiring profile group')
    created = product_client.post(URL, json=body(group_id=group.group_id)).json
    with pytest.raises(IntegrityError):
        Groups.delete().where(Groups.group_id == group.group_id).execute()
    assert profiles.resolve(created['id'], group.group_id).credentials['password']
    profiles.delete(created['id'], group_id=group.group_id, role=1,
                    actor_id=product.admin.user_id, revision=1)
    Groups.delete().where(Groups.group_id == group.group_id).execute()
    replacement = Groups.create(name='Replacement profile group')
    assert replacement.group_id == group.group_id
    assert profiles.list_profiles(replacement.group_id) == []


def test_scope_reference_cannot_be_omitted_for_an_owned_profile(product):
    from peewee import IntegrityError
    with pytest.raises(IntegrityError, match='CHECK'):
        ConnectionProfile.create(group_id=2, name='Invalid orphan', settings='{}',
                                 credentials_encrypted='synthetic', created_by=product.admin.user_id)


def test_refused_group_deletion_preserves_oidc_memberships_and_settings(product_client, product):
    from app.modules.db import group as groups
    from app.modules.db.db_model import Groups, OidcGroupMapping, Setting
    group = Groups.create(name='Group with retained profile')
    created = product_client.post(URL, json=body(group_id=group.group_id)).json
    mapping = OidcGroupMapping.create(provider_id=999, external_group='synthetic-mapping',
                                      group_id=group.group_id, role_id=2, active=1, priority=1)
    UserGroups.create(user_id=product.admin.user_id, user_group_id=group.group_id, user_role_id=2)
    Setting.create(param='synthetic-scope', value='retained', section='main', desc='Test setting', group_id=group.group_id)
    with pytest.raises(Exception, match='FOREIGN KEY'):
        groups.delete_group(group.group_id)
    assert OidcGroupMapping.get_by_id(mapping.id)
    assert UserGroups.select().where(UserGroups.user_group_id == group.group_id).exists()
    assert Setting.select().where(Setting.group_id == group.group_id).exists()
    profiles.delete(created['id'], group_id=group.group_id, role=1,
                    actor_id=product.admin.user_id, revision=1)
    assert groups.delete_group(group.group_id) is True
    assert not OidcGroupMapping.select().where(OidcGroupMapping.id == mapping.id).exists()
    assert not UserGroups.select().where(UserGroups.user_group_id == group.group_id).exists()
    assert not Setting.select().where(Setting.group_id == group.group_id).exists()
