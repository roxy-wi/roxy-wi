"""A verified legacy password cannot overwrite a newer account state."""

import pytest

from app.modules.db.db_model import User
from app.modules.roxywi import auth
from app.modules.roxy_wi_tools import Tools
from app.modules.roxywi.exception import RoxywiPublicError

PASSWORD = 'LegacyVerifiedPassword!'
# Pre-existing legacy database value; new password hashes always use scrypt.
LEGACY_DATABASE_HASH = 'e1846d46d83f9c9fb336fc834f407925'


@pytest.mark.parametrize('change', ['password_reset', 'replacement', 'disabled', 'renamed', 'ldap'])
def test_legacy_rehash_rejects_changed_account(app, product, monkeypatch, change):
    legacy = LEGACY_DATABASE_HASH
    User.update(password=legacy).where(User.user_id == product.admin.user_id).execute()
    replacement_hash = Tools.get_hash('AdministratorResetPassword!')
    original_check = Tools.check_password
    expected = {}

    def change_after_verification(password, stored):
        result = original_check(password, stored)
        if change == 'replacement':
            original_id = product.admin.user_id
            User.delete().where(User.user_id == original_id).execute()
            row = User.create(user_id=original_id, username='replacement', email='replacement@example.test',
                              password=replacement_hash, role_id='3', group_id='1',
                              ldap_user=0, enabled=1)
            assert row.user_id == original_id
            expected.update(password=replacement_hash, username='replacement')
        else:
            updates = {'password': replacement_hash} if change == 'password_reset' else {
                'enabled': 0} if change == 'disabled' else {
                'username': 'renamed-account'} if change == 'renamed' else {'ldap_user': 1}
            User.update(**updates).where(User.user_id == product.admin.user_id).execute()
            expected.update(password=replacement_hash if change == 'password_reset' else legacy)
        return result

    monkeypatch.setattr(Tools, 'check_password', change_after_verification)
    with app.test_request_context('/login'), pytest.raises(RoxywiPublicError):
        auth.check_user_password('admin', PASSWORD)
    current = User.get_by_id(product.admin.user_id)
    assert current.password == expected['password']
    if change == 'replacement':
        assert current.username == expected['username']
    if change == 'disabled':
        assert current.enabled == 0


def test_legacy_rehash_success_is_preserved(app, product):
    legacy = LEGACY_DATABASE_HASH
    User.update(password=legacy).where(User.user_id == product.admin.user_id).execute()
    with app.test_request_context('/login'):
        result = auth.check_user_password('admin', PASSWORD)
    current = User.get_by_id(product.admin.user_id)
    assert result['user'] == product.admin.user_id
    assert current.password != legacy
    assert Tools.check_password(PASSWORD, current.password) == (True, False)
