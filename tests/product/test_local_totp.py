"""Local MFA real database/HTTP tests, including cross-worker one-use semantics."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import os
import subprocess
import sys

import pyotp
import pytest
from flask_jwt_extended import decode_token, verify_jwt_in_request

from app.modules.authentication import security, totp
from app.modules.db.db_model import (AuthenticationChallenge, AuthenticationPolicy, RecoveryCode,
                                     TotpCredential, User, UserGroups, UserSecurity, AuthenticationEvent)
from app.modules.roxywi import auth
from app.modules.roxy_wi_tools import Tools
from app.modules.server.ssh import decrypt_password

PASSWORD = 'TestBootstrapPassword!'
# Pre-existing legacy DB fixture, shared with test_password_rehash_races.py.
# New passwords use scrypt; this known value exercises compatibility only.
LEGACY_PASSWORD = 'LegacyVerifiedPassword!'
LEGACY_DATABASE_HASH = 'e1846d46d83f9c9fb336fc834f407925'


@pytest.fixture
def clock(monkeypatch):
    value = [1893456000]
    monkeypatch.setattr(security, 'now', lambda: value[0])
    return value


def csrf(client):
    client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value


def setup(client, product, clock):
    prepared = client.post('/auth/totp/setup', json={'password': PASSWORD})
    assert prepared.status_code == 200, prepared.get_json()
    data = prepared.get_json()
    confirmed = client.post('/auth/totp/confirm', json={'challenge': data['challenge'],
        'otp': pyotp.TOTP(data['secret']).at(clock[0])})
    assert confirmed.status_code == 200, confirmed.get_json()
    csrf(client)
    clock[0] += 30
    return data['secret'], confirmed.get_json()['recovery_codes']


def login(client, api=False, password=PASSWORD):
    return client.post('/api/login' if api else '/login', json={'login':'admin',
        'password' if api else 'pass':password, 'next':'/security'})


def complete(client, challenge, secret, clock, api=False, recovery=None):
    data = {'challenge':challenge, 'channel':'api' if api else 'web'}
    data['recovery_code' if recovery else 'otp'] = recovery or pyotp.TOTP(secret).at(clock[0])
    return client.post('/auth/login/complete', json=data)


def test_enrollment_confirms_before_activating_and_encrypts_setup(product_client, product, clock):
    response = product_client.post('/auth/totp/setup', json={'password':PASSWORD})
    assert response.status_code == 200
    data = response.get_json()
    assert data['qr'].startswith('data:image/png;base64,')
    assert response.headers['Cache-Control'] == 'no-store'
    assert not totp.has_factor(product.admin.user_id)
    challenge = AuthenticationChallenge.get_by_id(security.digest(data['challenge']))
    assert data['secret'] not in challenge.payload and data['challenge'] not in challenge.token_hash
    assert data['secret'] in decrypt_password(challenge.payload)
    invalid = product_client.post('/auth/totp/confirm', json={'challenge':data['challenge'],'otp':'invalid'})
    assert invalid.status_code == 400 and not totp.has_factor(product.admin.user_id)
    valid = product_client.post('/auth/totp/confirm', json={'challenge':data['challenge'],'otp':pyotp.TOTP(data['secret']).at(clock[0])})
    assert valid.status_code == 200
    credential = TotpCredential.get_by_id(product.admin.user_id)
    assert credential.secret_encrypted != data['secret']
    codes = valid.get_json()['recovery_codes']
    assert len(codes) == 10 and len(codes[0].replace('-','')) == 32
    assert all(row.digest not in codes and row.digest != code for row,code in zip(RecoveryCode.select(),codes))
    csrf(product_client)
    assert product_client.post('/auth/totp/confirm',json={'challenge':data['challenge'],'otp':pyotp.TOTP(data['secret']).at(clock[0])}).status_code == 400


def test_web_and_api_password_only_cannot_issue_full_credentials(app, product_client, product, clock):
    secret, _ = setup(product_client, product, clock)
    for api in (False,True):
        client = app.test_client()
        started = login(client,api)
        assert started.status_code == 202
        assert started.get_json()['status'] == 'mfa_required'
        assert 'access_token' not in started.get_json()
        assert client.get_cookie('access_token_cookie') is None
        assert client.get('/api/swagger').status_code == 401
        wrong = client.post('/auth/login/complete',json={'challenge':started.get_json()['challenge'],'channel':'api' if api else 'web','otp':'not-code'})
        assert wrong.status_code == 401
        done = complete(client,started.get_json()['challenge'],secret,clock,api)
        assert done.status_code == 200, done.get_json()
        if api:
            token = done.get_json()['access_token']
            assert client.get('/api/swagger',headers={'Authorization':'Bearer '+token}).status_code == 200
        else:
            assert client.get_cookie('access_token_cookie')
        assert complete(client,started.get_json()['challenge'],secret,clock,api).status_code == 401
        clock[0] += 30


def test_totp_replay_across_different_challenges(app, product_client, product, clock):
    secret,_=setup(product_client,product,clock)
    clients=[app.test_client(),app.test_client()]
    starts=[login(c).get_json()['challenge'] for c in clients]
    assert complete(clients[0],starts[0],secret,clock).status_code == 200
    assert complete(clients[1],starts[1],secret,clock).status_code == 401


def test_adjacent_time_steps_and_monotonic_replay(product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    user=product.admin
    assert totp.verify_factor(user,{'otp':pyotp.TOTP(secret).at(clock[0]-30)}) is False  # setup code consumed
    assert totp.verify_factor(user,{'otp':pyotp.TOTP(secret).at(clock[0]+30)}) is True
    assert totp.verify_factor(user,{'otp':pyotp.TOTP(secret).at(clock[0])}) is False
    assert totp.verify_factor(user,{'otp':pyotp.TOTP(secret).at(clock[0]+90)}) is False


def test_recovery_code_is_hashed_one_use_and_password_required(app,product_client,product,clock):
    secret,codes=setup(product_client,product,clock)
    clients=[app.test_client(),app.test_client()]
    starts=[login(c).get_json()['challenge'] for c in clients]
    assert complete(clients[0],starts[0],secret,clock,recovery=codes[0]).status_code == 200
    assert complete(clients[1],starts[1],secret,clock,recovery=codes[0]).status_code == 401
    assert RecoveryCode.get(RecoveryCode.digest==security.digest(codes[0].replace('-',''))).used_at
    assert clients[1].post('/auth/login/complete',json={'recovery_code':codes[1]}).status_code == 401


def test_challenge_purpose_expiry_and_browser_binding(app,product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    first,other=app.test_client(),app.test_client()
    token=login(first).get_json()['challenge']
    assert complete(other,token,secret,clock).status_code==401
    assert complete(first,token,secret,clock,api=True).status_code==401
    clock[0]+=301
    assert complete(first,token,secret,clock).status_code==401


def test_gate_persists_across_new_challenges_and_locks_after_five(app,product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    client=app.test_client()
    for _ in range(5):
        token=login(client).get_json()['challenge']
        assert client.post('/auth/login/complete',json={'challenge':token,'otp':'invalid'}).status_code==401
    gate=UserSecurity.get_by_id(product.admin.user_id)
    assert gate.blocked_until==clock[0]+300
    token=login(client).get_json()['challenge']
    assert complete(client,token,secret,clock).status_code==401
    clock[0]+=301
    token=login(client).get_json()['challenge']
    assert complete(client,token,secret,clock).status_code==200


def test_sensitive_action_proofs_are_one_use_bound_to_session_purpose_and_epoch(app,product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    proof=product_client.post('/auth/reauthenticate',json={'purpose':'personal_token.create','password':PASSWORD,'otp':pyotp.TOTP(secret).at(clock[0])})
    assert proof.status_code==200
    token=proof.get_json()['reauth_token']
    with app.test_request_context(headers={'Cookie':'access_token_cookie='+product_client.get_cookie('access_token_cookie').value}):
        verify_jwt_in_request(locations=['cookies'])
        with pytest.raises(Exception):
            security.require_sensitive_action(product.admin,{'reauth_token':token},'totp.remove')
        security.require_sensitive_action(product.admin,{'reauth_token':token})
        with pytest.raises(Exception):
            security.require_sensitive_action(product.admin,{'reauth_token':token})
    assert product_client.post('/auth/reauthenticate',json={'purpose':'personal_token.create','password':PASSWORD}).status_code==400


def test_factor_management_requires_password_and_csrf(app,product_client,product,clock):
    assert product_client.post('/auth/totp/setup',json={}).status_code==400
    no_csrf=app.test_client()
    no_csrf.set_cookie('access_token_cookie',product_client.get_cookie('access_token_cookie').value)
    assert no_csrf.post('/auth/totp/setup',json={'password':PASSWORD}).status_code==401
    secret,_=setup(product_client,product,clock)
    assert product_client.delete('/auth/totp',json={'password':PASSWORD}).status_code==400
    assert totp.has_factor(product.admin.user_id)


def test_password_change_and_console_reset_invalidate_existing_sessions_and_challenges(app,product_client,product,clock):
    secret,codes=setup(product_client,product,clock)
    client=app.test_client(); token=login(client).get_json()['challenge']
    old_epoch=security.user_epoch(product.admin.user_id)
    security.console_reset('admin','lost-device')
    assert security.user_epoch(product.admin.user_id)==old_epoch+1
    assert not totp.has_factor(product.admin.user_id)
    assert not RecoveryCode.select().where(RecoveryCode.user_id==product.admin.user_id).exists()
    assert product_client.get('/auth/security').status_code==401
    assert complete(client,token,secret,clock).status_code==401
    assert AuthenticationEvent.select().where(AuthenticationEvent.event=='authentication.console_reset.lost-device').exists()
    plain=app.test_client(); assert login(plain).status_code==200
    User.update(password=Tools.get_hash('ChangedPassword!')).where(User.user_id==product.admin.user_id).execute()
    assert plain.get('/api/swagger').status_code==401


def test_group_switch_preserves_authentication_time(app,product_client,product,clock):
    setup(product_client,product,clock)
    old=product_client.get_cookie('access_token_cookie').value
    with app.test_request_context(headers={'Cookie':'access_token_cookie='+old}):
        verify_jwt_in_request(locations=['cookies'])
        clock[0]+=120
        refreshed=auth.create_jwt_token({'user':product.admin.user_id,'group':'2'})
        before,after=decode_token(old),decode_token(refreshed)
        for key in security.PROOF_FIELDS:
            assert before[key]==after[key]


def test_policy_invalidates_existing_sessions_and_grace_then_restricted_enrollment(app,product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    user=User.create(username='operator',email='operator@example.test',password=Tools.get_hash(PASSWORD),role_id='3',group_id='1',ldap_user=0,enabled=1)
    UserGroups.create(user_id=user.user_id,user_group_id=1,user_role_id=3)
    other=app.test_client()
    assert other.post('/login',json={'login':'operator','pass':PASSWORD}).status_code==200
    saved=product_client.post('/auth/policy',json={'mode':'all','grace_days':1,'password':PASSWORD,'otp':pyotp.TOTP(secret).at(clock[0])})
    assert saved.status_code==200
    assert other.get('/api/swagger').status_code==401
    assert product_client.get('/auth/security').status_code==401
    grace=app.test_client();assert grace.post('/login',json={'login':'operator','pass':PASSWORD}).status_code==200
    clock[0]+=86401
    assert grace.get('/api/swagger').status_code==401
    enrolled=app.test_client()
    started=enrolled.post('/login',json={'login':'operator','pass':PASSWORD,'next':'/security'})
    assert started.status_code==202 and started.get_json()['status']=='enrollment_required'
    assert enrolled.get_cookie('access_token_cookie') is None
    prepared=enrolled.post('/auth/enrollment/start',json={'challenge':started.get_json()['challenge']})
    assert prepared.status_code==200
    data=prepared.get_json()
    confirmed=enrolled.post('/auth/enrollment/confirm',json={'challenge':data['challenge'],'otp':pyotp.TOTP(data['secret']).at(clock[0])})
    assert confirmed.status_code==200,confirmed.get_json()
    assert len(confirmed.get_json()['recovery_codes'])==10
    assert enrolled.get('/auth/security').status_code==200


def test_required_policy_blocks_last_factor_removal(product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    AuthenticationPolicy.update(mode='all',grace_until=clock[0]+100).where(AuthenticationPolicy.id==1).execute()
    response=product_client.delete('/auth/totp',json={'password':PASSWORD,'otp':pyotp.TOTP(secret).at(clock[0])})
    assert response.status_code==400
    assert totp.has_factor(product.admin.user_id)


def test_regenerating_recovery_revokes_old_set(product_client,product,clock):
    secret,codes=setup(product_client,product,clock)
    response=product_client.post('/auth/recovery-codes',json={'password':PASSWORD,'otp':pyotp.TOTP(secret).at(clock[0])})
    assert response.status_code==200
    assert not security.verify_recovery(product.admin,codes[0])
    assert security.verify_recovery(product.admin,response.get_json()['recovery_codes'][0])


def test_two_workers_cannot_use_same_totp_or_recovery_code(product_client,product,clock):
    secret,codes=setup(product_client,product,clock)
    for factor in ({'otp':pyotp.TOTP(secret).at(clock[0])},{'recovery_code':codes[0]}):
        tokens=[security.issue_challenge(product.admin,'concurrency') for _ in range(2)]
        def worker(token):
            with product.db.connection_context():
                return bool(security.consume_challenge(token,'concurrency',verify=lambda user,payload:security.verify_factor(user,factor)))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,tokens))
        assert sorted(results)==[False,True]


def test_real_processes_share_atomic_recovery_consumption(product_client,product,clock):
    _,codes=setup(product_client,product,clock)
    source="""import os; os.environ['ROXYWI_PROCESS_ROLE']='migrate'
from app.modules.authentication import security
from app.modules.db.db_model import User
print(int(security.verify_recovery(User.get_by_id(int(os.environ['TEST_USER'])),os.environ['TEST_RECOVERY'])))
"""
    env=dict(os.environ,TEST_USER=str(product.admin.user_id),TEST_RECOVERY=codes[0])
    processes=[subprocess.Popen([sys.executable,'-c',source],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    results=[p.communicate(timeout=20) for p in processes]
    assert all(p.returncode==0 for p in processes),results
    assert sorted(out.strip() for out,err in results)==['0','1']


def test_migrations_idempotent_and_user_delete_cascades(product_client,product,clock):
    setup(product_client,product,clock)
    for name in ('20261029040000_local_authentication','20261029050000_local_totp'):
        migration=import_module('app.modules.db.migrations.'+name)
        migration.up();migration.up()
    User.delete().where(User.user_id==product.admin.user_id).execute()
    assert not TotpCredential.select().exists()
    assert not RecoveryCode.select().exists()
    assert not UserSecurity.select().where(UserSecurity.user_id==product.admin.user_id).exists()


def test_fifth_challenge_attempt_can_succeed_but_cannot_replay(app,product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    client=app.test_client(); token=login(client).get_json()['challenge']
    for _ in range(4):
        assert client.post('/auth/login/complete',json={'challenge':token,'otp':'bad'}).status_code==401
    assert complete(client,token,secret,clock).status_code==200
    assert complete(client,token,secret,clock).status_code==401


def test_failed_setup_confirmation_counts_and_cannot_be_bruteforced(product_client,product,clock):
    data=product_client.post('/auth/totp/setup',json={'password':PASSWORD}).get_json()
    for attempt in range(5):
        assert product_client.post('/auth/totp/confirm',json={'challenge':data['challenge'],'otp':'invalid'}).status_code==400
        assert AuthenticationChallenge.get_by_id(security.digest(data['challenge'])).attempts==attempt+1
    assert product_client.post('/auth/totp/confirm',json={'challenge':data['challenge'],'otp':pyotp.TOTP(data['secret']).at(clock[0])}).status_code==400
    assert not totp.has_factor(product.admin.user_id)


def test_recovery_login_revokes_old_sessions_and_mints_committed_epoch(app,product_client,product,clock):
    secret,codes=setup(product_client,product,clock)
    old_epoch=security.user_epoch(product.admin.user_id)
    client=app.test_client();challenge=login(client).get_json()['challenge']
    done=complete(client,challenge,secret,clock,recovery=codes[0])
    assert done.status_code==200
    assert security.user_epoch(product.admin.user_id)==old_epoch+1
    assert product_client.get('/auth/security').status_code==401
    assert client.get('/auth/security').status_code==200
    with app.app_context():
        assert decode_token(client.get_cookie('access_token_cookie').value)['auth_epoch']==old_epoch+1


def test_admin_policy_covers_group_admin_membership_outside_active_group(product,clock):
    user=User.create(username='otheradmin',email='otheradmin@example.test',password=Tools.get_hash(PASSWORD),role_id='4',group_id='1',ldap_user=0,enabled=1)
    UserGroups.create(user_id=user.user_id,user_group_id=2,user_role_id=2)
    AuthenticationPolicy.get_or_create(id=1)
    AuthenticationPolicy.update(mode='admin',grace_until=0).execute()
    assert security.policy_applies(user)
    assert security.enrollment_required(user)


def test_no_factor_grace_session_only_allows_security_bootstrap_after_expiry(product_client,product,clock):
    AuthenticationPolicy.update(mode='all',grace_until=clock[0]+30).execute()
    clock[0]+=31
    assert product_client.get('/auth/security').status_code==200
    assert product_client.get('/security').status_code==200
    assert product_client.get('/api/swagger').status_code==401
    assert product_client.get('/admin').status_code==401
    assert product_client.post('/auth/totp/setup',json={'password':PASSWORD}).status_code==200


def test_pat_tag_without_pat_provider_cannot_bypass_mfa(app,product_client,product,clock):
    from flask_jwt_extended import create_access_token
    setup(product_client,product,clock)
    with app.app_context():
        token=create_access_token(str(product.admin.user_id),additional_claims={'group':'1','credential_type':'pat'})
    client=app.test_client()
    assert client.get('/api/swagger',headers={'Authorization':'Bearer '+token}).status_code==401


def test_proof_verified_before_reset_cannot_adopt_new_epoch(app,product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    token=security.issue_challenge(product.admin,'proof-snapshot')
    result=security.consume_challenge(token,'proof-snapshot',verify=lambda user,payload:totp.verify_factor(user,{'otp':pyotp.TOTP(secret).at(clock[0])}))
    assert result
    proof=security.proof_from_challenge(result[1],'totp')
    security.revoke_sessions(product.admin)
    assert proof['auth_epoch'] != security.user_epoch(product.admin.user_id)
    assert not security.validate_session(dict(user_id=product.admin.user_id,group='1',**proof))


def test_challenges_bounded_and_expired_secrets_pruned(product,clock):
    tokens=[security.issue_challenge(product.admin,'capacity') for _ in range(20)]
    with pytest.raises(Exception):
        security.issue_challenge(product.admin,'capacity')
    clock[0]+=301
    security.issue_challenge(product.admin,'capacity')
    assert AuthenticationChallenge.select().count()==1
    assert security.consume_challenge(tokens[0],'capacity') is None


def test_security_ui_and_totp_work_without_subscription_or_oidc(product_client,product,clock,monkeypatch):
    from app.modules.roxywi import common
    def unavailable():
        raise RuntimeError('Synthetic subscription service outage')
    monkeypatch.setattr(common,'return_user_subscription',unavailable)
    assert product_client.get('/security').status_code==200
    secret,_=setup(product_client,product,clock)
    assert product_client.get('/auth/security').status_code==200


def test_rotation_covers_pending_and_active_totp_and_rolls_back_invalid_secret(product_client,product,clock):
    from cryptography.fernet import Fernet, InvalidToken
    old_key=Fernet(os.environ['ROXYWI_SECRET_PHRASE'].encode())
    new_key=Fernet(Fernet.generate_key())
    secret,_=setup(product_client,product,clock)
    token=security.issue_challenge(product.admin,'rotation',{'private':'Synthetic setup material'})
    with product.db.atomic():
        assert security.rotate_encrypted_state(old_key,new_key)==2
    row=TotpCredential.get_by_id(product.admin.user_id)
    challenge=AuthenticationChallenge.get_by_id(security.digest(token))
    assert new_key.decrypt(row.secret_encrypted.encode()).decode()==secret
    assert b'Synthetic setup material' in new_key.decrypt(challenge.payload.encode())
    assert security.rotate_encrypted_state(old_key,new_key)==0
    AuthenticationChallenge.update(payload='invalid').execute()
    with pytest.raises(InvalidToken):
        with product.db.atomic():
            security.rotate_encrypted_state(new_key,old_key)
    assert new_key.decrypt(TotpCredential.get_by_id(product.admin.user_id).secret_encrypted.encode()).decode()==secret


def test_security_management_rejects_header_and_cookie_mixed_identities(app,product_client,product,clock):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token=create_access_token(str(product.admin.user_id),additional_claims={'group':'1'})
    headers={'Authorization':'Bearer '+token}
    assert product_client.get('/auth/security',headers=headers).status_code==400
    assert product_client.get('/security',headers=headers).status_code==400
    assert product_client.post('/auth/reauthenticate',headers=headers,json={'purpose':'totp.setup','password':PASSWORD}).status_code==400
    assert product_client.post('/auth/policy',headers=headers,json={'mode':'off','password':PASSWORD}).status_code==400


def test_policy_admin_status_and_update_use_current_membership(product_client,product,clock):
    UserGroups.update(user_role_id=3).where(UserGroups.user_id==product.admin.user_id).execute()
    assert product_client.get('/auth/security').get_json()['admin'] is False
    assert product_client.post('/auth/policy',json={'mode':'off','password':PASSWORD}).status_code==403


def test_real_processes_share_atomic_totp_challenge_and_counter(product_client,product,clock):
    secret,_=setup(product_client,product,clock)
    tokens=[security.issue_challenge(product.admin,'process-otp') for _ in range(2)]
    source="""import os; os.environ['ROXYWI_PROCESS_ROLE']='migrate'
from app.modules.authentication import security
security.now=lambda:int(os.environ['TEST_TIME'])
result=security.consume_challenge(os.environ['TEST_CHALLENGE'],'process-otp',verify=lambda user,payload:security.verify_factor(user,{'otp':os.environ['TEST_OTP']}))
print(int(bool(result)))
"""
    env=dict(os.environ,TEST_TIME=str(clock[0]),TEST_OTP=pyotp.TOTP(secret).at(clock[0]))
    processes=[subprocess.Popen([sys.executable,'-c',source],env=dict(env,TEST_CHALLENGE=token),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for token in tokens]
    results=[p.communicate(timeout=20) for p in processes]
    assert all(p.returncode==0 for p in processes),results
    assert sorted(out.strip() for out,err in results)==['0','1']


def test_recovery_can_replace_lost_totp_under_required_policy_without_password_only_gap(product_client,product,clock):
    old_secret,codes=setup(product_client,product,clock)
    AuthenticationPolicy.update(mode='all',grace_until=0).execute()
    epoch=security.user_epoch(product.admin.user_id)
    prepared=product_client.post('/auth/totp/setup',json={'password':PASSWORD,'recovery_code':codes[0]})
    assert prepared.status_code==200
    data=prepared.get_json()
    assert decrypt_password(TotpCredential.get_by_id(product.admin.user_id).secret_encrypted)==old_secret
    assert security.user_epoch(product.admin.user_id)==epoch
    assert data['secret'] != old_secret
    confirmed=product_client.post('/auth/totp/confirm',json={'challenge':data['challenge'],'otp':pyotp.TOTP(data['secret']).at(clock[0])})
    assert confirmed.status_code==200
    assert decrypt_password(TotpCredential.get_by_id(product.admin.user_id).secret_encrypted)==data['secret']
    assert security.user_epoch(product.admin.user_id)==epoch+1
    assert not security.verify_recovery(product.admin,codes[1])


def test_local_authentication_history_has_age_and_count_bounds(product,clock,monkeypatch):
    monkeypatch.setattr(security,'MAX_LOCAL_EVENTS',3)
    for _ in range(6):
        security.record(product.admin.user_id,'authentication.test',external=False)
    assert AuthenticationEvent.select().count()==3
    clock[0]+=91*86400
    security.record(product.admin.user_id,'authentication.test',external=False)
    assert AuthenticationEvent.select().count()==1


def test_reset_between_sensitive_proof_and_setup_issuance_cannot_rebind_old_proof(product_client,product,clock,monkeypatch):
    original=security.require_sensitive_action
    def reset_after(*args,**kwargs):
        original(*args,**kwargs)
        security.console_reset('admin','compromise')
    monkeypatch.setattr(security,'require_sensitive_action',reset_after)
    response=product_client.post('/auth/totp/setup',json={'password':PASSWORD})
    assert response.status_code==400
    assert not AuthenticationChallenge.select().where(AuthenticationChallenge.purpose=='totp:setup').exists()
    assert not totp.has_factor(product.admin.user_id)


def test_reset_between_enrollment_password_proof_and_setup_issuance_cannot_rebind(app,product_client,product,clock,monkeypatch):
    AuthenticationPolicy.update(mode='all',grace_until=0).execute()
    client=app.test_client()
    started=login(client).get_json()
    assert started['status']=='enrollment_required'
    original=security.consume_challenge
    def reset_after(*args,**kwargs):
        result=original(*args,**kwargs)
        if result and args[1]=='login:web':
            security.console_reset('admin','compromise')
        return result
    monkeypatch.setattr(security,'consume_challenge',reset_after)
    response=client.post('/auth/enrollment/start',json={'challenge':started['challenge']})
    assert response.status_code==400
    assert not AuthenticationChallenge.select().where(AuthenticationChallenge.purpose=='totp:enrollment').exists()


def test_deleted_account_id_reuse_rejects_legacy_and_cloned_password_modern_jwt_after_restart(app,product,clock):
    from app import initialize_database
    user=User.create(username='oldaccount',email='oldaccount@example.test',password=Tools.get_hash(PASSWORD),role_id='3',group_id='1',ldap_user=0,enabled=1)
    row=security.state(user)
    # Model an actual migration-era account plus a modern password session.
    UserSecurity.update(legacy_allowed=True).where(UserSecurity.user_id==user.user_id).execute()
    legacy={'user_id':str(user.user_id),'group':'1'}
    modern=dict(legacy,**security.login_proof(user,'password',expected=security.capture_account(user.user_id)[1]))
    assert security.validate_session(legacy)
    assert security.validate_session(modern)
    original_id=user.user_id
    cloned_hash=user.password
    user.delete_instance()
    replacement=User.create(username='replacement',email='replacement@example.test',password=cloned_hash,role_id='3',group_id='1',ldap_user=0,enabled=1)
    assert replacement.user_id==original_id
    assert not security.validate_session(legacy)
    assert not security.validate_session(modern)
    replacement_state=security.state(replacement)
    assert not replacement_state.legacy_allowed and replacement_state.account_id!=row.account_id
    # Normal restart and an idempotent migration cannot grant legacy eligibility.
    UserSecurity.delete().where(UserSecurity.user_id==replacement.user_id).execute()
    initialize_database()
    import_module('app.modules.db.migrations.20261029040000_local_authentication').up()
    assert not security.validate_session(legacy)
    assert not security.validate_session(modern)


def test_missing_bootstrap_state_is_not_reseeded_after_account_replacement(app,product,clock):
    from app import initialize_database
    legacy={'user_id':str(product.admin.user_id),'group':'1'}
    assert security.validate_session(legacy)
    original_id=product.admin.user_id
    # Delete all users so the bootstrap numeric ID is reused.
    User.delete().execute()
    replacement=User.create(username='newbootstrap',email='newbootstrap@example.test',password=Tools.get_hash(PASSWORD),role_id='1',group_id='1',ldap_user=0,enabled=1)
    assert replacement.user_id==original_id
    initialize_database()
    assert not security.validate_session(legacy)


def test_external_audit_quota_cannot_rollback_denial_gate_or_local_event(product,clock,monkeypatch):
    from types import SimpleNamespace
    class AuditStorageUnavailable(Exception):
        pass
    calls=[]
    def unavailable(*args,**kwargs):
        calls.append(kwargs)
        raise AuditStorageUnavailable('Synthetic full external audit queue')
    adapter=SimpleNamespace(record=unavailable,AuditStorageUnavailable=AuditStorageUnavailable)
    original_spec=security.importlib.util.find_spec
    original_import=security.importlib.import_module
    monkeypatch.setattr(security.importlib.util,'find_spec',lambda name:object() if name=='app.modules.audit' else original_spec(name))
    monkeypatch.setattr(security.importlib,'import_module',lambda name:adapter if name=='app.modules.audit.events' else original_import(name))
    def denied(user,payload):
        security.record(user.user_id,'authentication.factor','denied',reason_code='invalid_factor',actor_verified=False)
        return False
    for _ in range(5):
        token=security.issue_challenge(product.admin,'audit-denied')
        assert security.consume_challenge(token,'audit-denied',verify=denied) is None
    assert UserSecurity.get_by_id(product.admin.user_id).blocked_until==clock[0]+300
    assert AuthenticationEvent.select().where(AuthenticationEvent.outcome=='denied').count()==5
    assert len(calls)==5 and all(call['user_id'] is None for call in calls)
    # Successful security mutation remains fail-closed on the same quota error.
    payload=totp.setup_payload(product.admin)
    with pytest.raises(AuditStorageUnavailable):
        with security.atomic():
            assert totp.activate(product.admin,payload,pyotp.TOTP(payload['secret']).at(clock[0]))
            security.record(product.admin.user_id,'authentication.totp.enrolled')
    assert not totp.has_factor(product.admin.user_id)


def test_new_ldap_account_still_gets_provider_owned_proof_without_local_mfa(app,product,clock,monkeypatch):
    user=User.create(username='directoryuser',email='directory@example.test',password=None,role_id='3',group_id='1',ldap_user=1,enabled=1)
    UserGroups.create(user_id=user.user_id,user_group_id=1,user_role_id=3)
    monkeypatch.setattr(auth,'check_in_ldap',lambda username,password:True)
    AuthenticationPolicy.update(mode='all',grace_until=0).execute()
    client=app.test_client()
    response=client.post('/login',json={'login':user.username,'pass':'DirectoryPassword!'})
    assert response.status_code==200
    assert client.get('/api/swagger').status_code==200
    with app.app_context():
        proof=decode_token(client.get_cookie('access_token_cookie').value)
    assert proof['auth_method']=='ldap'
    assert proof['auth_account']==security.user_account_id(user.user_id)
    assert not security.state(user).legacy_allowed


def test_legacy_rehash_cannot_overwrite_concurrent_password_reset(app,product,clock,monkeypatch):
    legacy=LEGACY_DATABASE_HASH
    User.update(password=legacy).where(User.user_id==product.admin.user_id).execute()
    replacement=Tools.get_hash('AdministratorResetPassword!')
    original=Tools.check_password
    def reset_after(password,stored):
        result=original(password,stored)
        assert result==(True,True)
        User.update(password=replacement).where(User.user_id==product.admin.user_id).execute()
        return result
    monkeypatch.setattr(Tools,'check_password',reset_after)
    client=app.test_client()
    response=login(client,password=LEGACY_PASSWORD)
    assert response.status_code==401
    assert User.get_by_id(product.admin.user_id).password==replacement
    assert client.get_cookie('access_token_cookie') is None


def test_upgrade_from_existing_master_schema_seeds_legacy_once(app,product,clock):
    from app import initialize_database
    from app.modules.db.migration_manager import Migration
    upgraded=User.create(username='existinguser',email='existinguser@example.test',password=Tools.get_hash(PASSWORD),role_id='3',group_id='1',ldap_user=0,enabled=1)
    # Model the pre-feature schema and its existing migration ledger.
    product.db.drop_tables([AuthenticationChallenge,RecoveryCode,TotpCredential,UserSecurity,AuthenticationEvent,AuthenticationPolicy])
    Migration.delete().where(Migration.name.in_(['20261029040000_local_authentication','20261029050000_local_totp'])).execute()
    initialize_database()
    for user in (product.admin,upgraded):
        row=UserSecurity.get_by_id(user.user_id)
        assert row.legacy_allowed and len(row.account_id)==32
        assert security.validate_session({'user_id':str(user.user_id),'group':'1'})
    assert AuthenticationPolicy.get_by_id(1).baseline_initialized
    assert not TotpCredential.select().exists()
    initialize_database()
    assert UserSecurity.select().count()==User.select().count()


def test_credential_fingerprint_is_keyed_and_independent_of_fernet_rotation(app,product,monkeypatch):
    import hashlib
    import hmac
    legacy=LEGACY_DATABASE_HASH
    User.update(password=legacy).where(User.user_id==product.admin.user_id).execute()
    user=User.get_by_id(product.admin.user_id)
    first=security.password_version(user)
    key=app.config['SECRET_KEY'].encode('utf-8')
    expected=hmac.new(key,b'roxywi.local-auth.password-version.v1\x00'+legacy.encode(),hashlib.sha256).hexdigest()
    assert first==expected
    assert first!=hashlib.sha256(legacy.encode()).hexdigest()
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE','SyntheticDifferentFernetKeyEnvironment')
    assert security.password_version(user)==first
    monkeypatch.setitem(app.config,'SECRET_KEY','DifferentStableApplicationKeyForThisTestOnly')
    assert security.password_version(user)!=first
