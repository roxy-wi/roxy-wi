import pytest
from flask_jwt_extended import create_access_token
import app.routes.pacemaker.routes as routes


@pytest.fixture
def authenticated(app, monkeypatch):
    params = {'user_id': 1, 'group_id': 1, 'user': 'admin', 'role': 1, 'lang': 'en',
              'user_services': '1 2 3 4 5 6'}
    monkeypatch.setattr(routes.auth, 'is_access_permit_to_service', lambda _service: True)
    import app.modules.roxywi.common as common
    monkeypatch.setattr(common, 'get_users_params', lambda **_kwargs: dict(params))
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    return params, {'Authorization': f'Bearer {token}'}
