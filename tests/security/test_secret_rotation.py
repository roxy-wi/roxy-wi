import uuid

import pytest
from cryptography.fernet import Fernet

from app.modules.db.db_model import (Cred, OidcProvider, LetsEncryptDnsProfile, PacemakerCluster,
    PacemakerChange, CertificateSource, OperationalAssessment, HaMaintenancePlan, ServedTlsMonitor, ManagedAclFeed, ManagedAclVersion)
from rotate_credential_secret import _fernet_from_environment, rotate_credentials


@pytest.mark.security
def test_credential_rotation_reencrypts_secret_fields_atomically(monkeypatch):
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_fernet = Fernet(old_key)
    password = old_fernet.encrypt(b'secret-password').decode('ascii')
    credential = Cred.create(
        name=f'rotation-{uuid.uuid4().hex}', username='root', password=password, group_id=1,
        passphrase=None, private_key=None
    )
    provider = OidcProvider.create(
        slug=f'rotation-{uuid.uuid4().hex}',
        label='Rotation test',
        client_id='roxy-wi',
        client_secret_encrypted=old_fernet.encrypt(b'oidc-client-secret').decode('ascii'),
        enabled=0,
    )
    profile = LetsEncryptDnsProfile.create(name=f'rotation-{uuid.uuid4().hex}', group_id=1,
        provider='cloudflare', credentials='fernet:' + old_fernet.encrypt(b'{"api_token":"dns-secret"}').decode('ascii'))
    source = CertificateSource.create(name='rotation-source', group_id=1, user_id=1, provider='certwarden',
        configuration='fernet:' + old_fernet.encrypt(b'{"private_key_api_key":"provider-secret"}').decode('ascii'))
    report=OperationalAssessment.create(group_id=1,user_id=1,kind='ha-readiness',subject='pacemaker:1',
        result='fernet:'+old_fernet.encrypt(b'{"checks":[]}').decode())
    maintenance=HaMaintenancePlan.create(group_id=1,user_id=1,provider='pacemaker',cluster_id=1,server_id=1,
        payload='fernet:'+old_fernet.encrypt(b'{"capacity_evidence":"test"}').decode())
    tls=ServedTlsMonitor.create(group_id=1,user_id=1,name="Rotation TLS",configuration="fernet:"+old_fernet.encrypt(b'{"ca_pem":"public"}').decode())
    feed=ManagedAclFeed.create(group_id=1,user_id=1,name='Rotation feed',configuration='fernet:'+old_fernet.encrypt(b'{"settings":{}}').decode())
    feed_version=ManagedAclVersion.create(group_id=1,user_id=1,feed_id=feed.id,feed_revision=1,entries=1,fingerprint='a'*64,
        content='fernet:'+old_fernet.encrypt(b'{"text":"192.0.2.0/24"}').decode(),details='fernet:'+old_fernet.encrypt(b'{"targets":[]}').decode())
    cluster = PacemakerCluster.create(name=f'rotation-{uuid.uuid4().hex}', group_id=1)
    change = PacemakerChange.create(cluster=cluster, user_id=1, base_digest='0' * 64,
        **{field: old_fernet.encrypt(b'<cib secret="fencing-secret"/>').decode('ascii')
           for field in ('candidate', 'previous', 'result', 'details')})
    monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE', old_key.decode('ascii'))
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', new_key.decode('ascii'))

    try:
        assert rotate_credentials() >= 4

        credential = Cred.get_by_id(credential.id)
        provider = OidcProvider.get_by_id(provider.id)
        assert Fernet(new_key).decrypt(credential.password.encode('ascii')) == b'secret-password'
        assert Fernet(new_key).decrypt(provider.client_secret_encrypted.encode('ascii')) == b'oidc-client-secret'
        rotated_profile = LetsEncryptDnsProfile.get_by_id(profile.id)
        assert Fernet(new_key).decrypt(rotated_profile.credentials.removeprefix('fernet:').encode()) == b'{"api_token":"dns-secret"}'
        rotated_source = CertificateSource.get_by_id(source.id)
        assert Fernet(new_key).decrypt(rotated_source.configuration.removeprefix('fernet:').encode()) == b'{"private_key_api_key":"provider-secret"}'
        assert Fernet(new_key).decrypt(OperationalAssessment.get_by_id(report.id).result.removeprefix('fernet:').encode())==b'{"checks":[]}'
        assert Fernet(new_key).decrypt(HaMaintenancePlan.get_by_id(maintenance.id).payload.removeprefix('fernet:').encode())==b'{"capacity_evidence":"test"}'
        assert Fernet(new_key).decrypt(ServedTlsMonitor.get_by_id(tls.id).configuration.removeprefix("fernet:").encode())==b'{"ca_pem":"public"}'
        assert Fernet(new_key).decrypt(ManagedAclFeed.get_by_id(feed.id).configuration.removeprefix('fernet:').encode())==b'{"settings":{}}'
        rotated_feed=ManagedAclVersion.get_by_id(feed_version.id)
        assert Fernet(new_key).decrypt(rotated_feed.content.removeprefix('fernet:').encode())==b'{"text":"192.0.2.0/24"}'
        assert Fernet(new_key).decrypt(rotated_feed.details.removeprefix('fernet:').encode())==b'{"targets":[]}'
        rotated_change = PacemakerChange.get_by_id(change.id)
        for field in ('candidate', 'previous', 'result', 'details'):
            assert Fernet(new_key).decrypt(getattr(rotated_change, field).encode()) == b'<cib secret="fencing-secret"/>'
        assert rotate_credentials() == 0  # A repeated rotation is safe.
    finally:
        Cred.delete().where(Cred.id == credential.id).execute()
        OidcProvider.delete().where(OidcProvider.id == provider.id).execute()
        LetsEncryptDnsProfile.delete().where(LetsEncryptDnsProfile.id == profile.id).execute()
        source.delete_instance()
        report.delete_instance()
        maintenance.delete_instance()
        tls.delete_instance()
        feed_version.delete_instance();feed.delete_instance()
        cluster.delete_instance(recursive=True)


@pytest.mark.security
def test_rotation_accepts_any_valid_non_placeholder_key(monkeypatch):
    valid_key = '_B8avTpFFL19M8P9VyTiX42NyeyUaneV26kyftB2E_4='
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', valid_key)

    assert isinstance(
        _fernet_from_environment('ROXYWI_SECRET_PHRASE'),
        Fernet,
    )


@pytest.mark.security
def test_rotation_rejects_change_me(monkeypatch):
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', 'CHANGE_ME')

    with pytest.raises(RuntimeError, match='must not be CHANGE_ME'):
        _fernet_from_environment('ROXYWI_SECRET_PHRASE')
