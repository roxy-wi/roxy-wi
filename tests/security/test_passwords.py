import hashlib
import re

import pytest

from app.modules.db.db_model import User, UserGroups
from app.modules.roxy_wi_tools import Tools
from app.modules.roxywi.auth import check_user_password


@pytest.mark.security
def test_new_password_hash_is_not_md5():
    password_hash = Tools.get_hash('A-long-test-password!')

    assert not re.fullmatch(r'[0-9a-f]{32}', password_hash)
    assert Tools.check_password('A-long-test-password!', password_hash) == (True, False)


@pytest.mark.security
def test_legacy_md5_password_is_rehashed_after_login(app):
    password = 'legacy-password'
    legacy_hash = hashlib.md5(password.encode('utf-8')).hexdigest()
    user = User.create(
        username='legacy-user', email='legacy@example.test', password=legacy_hash,
        role_id='3', group_id='1', enabled=1, ldap_user=0,
    )
    UserGroups.create(user_id=user.user_id, user_group_id=1, user_role_id=3)

    with app.test_request_context('/login'):
        result = check_user_password('legacy-user', password)

    user = User.get_by_id(user.user_id)
    assert result['user'] == user.user_id
    assert user.password != legacy_hash
    assert Tools.check_password(password, user.password) == (True, False)
