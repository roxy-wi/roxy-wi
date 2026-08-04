import uuid

import pytest

from app.api.routes import routes as api_routes
from app.modules.db.db_model import User, UserGroups
from app.modules.roxy_wi_tools import Tools


@pytest.fixture()
def api_user():
    suffix = uuid.uuid4().hex
    password = 'API-test-password!'
    user = User.create(
        username=f'api-user-{suffix}',
        email=f'api-user-{suffix}@example.test',
        password=Tools.get_hash(password),
        role_id='1',
        group_id='1',
        enabled=1,
        ldap_user=0,
    )
    UserGroups.create(user_id=user.user_id, user_group_id=1, user_role_id=1)

    yield user, password

    UserGroups.delete().where(UserGroups.user_id == user.user_id).execute()
    User.delete().where(User.user_id == user.user_id).execute()


@pytest.fixture(autouse=True)
def active_api_subscription(monkeypatch):
    monkeypatch.setattr(
        api_routes.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'business'},
    )


@pytest.mark.security
def test_api_login_returns_token_for_valid_credentials(client, api_user):
    user, password = api_user

    response = client.post('/api/login', json={
        'login': user.username,
        'password': password,
    })

    assert response.status_code == 200
    access_token = response.get_json()['access_token']
    assert isinstance(access_token, str)
    assert access_token

    protected_response = client.get(
        '/api/swagger',
        headers={'Authorization': f'Bearer {access_token}'},
    )
    assert protected_response.status_code == 200


@pytest.mark.security
def test_api_login_rejects_invalid_password(client, api_user):
    user, _password = api_user

    response = client.post('/api/login', json={
        'login': user.username,
        'password': 'incorrect-password',
    })

    assert response.status_code == 401
    assert response.get_json()['status'] == 'failed'


@pytest.mark.security
def test_other_api_endpoints_still_require_authentication(client):
    response = client.get('/api/swagger')

    assert response.status_code == 401
    assert response.get_json()['status'] == 'failed'
