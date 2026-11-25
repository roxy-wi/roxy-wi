"""Prepared fixture data must never replace production hashing or verification."""
import secrets

from app import create_db
from app.modules.db.db_model import User
from app.modules.roxy_wi_tools import Tools


def test_bootstrap_fixture_uses_real_modern_hashes_and_restores_production_tools(product):
    # The scoped preparation proxies are gone before the test receives its DB.
    assert create_db.Tools is Tools
    assert create_db.secrets is secrets
    admin = User.get_by_id(product.admin.user_id)
    other_accounts = list(User.select().where(User.username.in_(['editor', 'guest'])))
    assert {(user.username, str(user.role_id)) for user in other_accounts} == {('editor', '2'), ('guest', '4')}
    hashes = [admin.password, *(user.password for user in other_accounts)]
    assert all(value.startswith('scrypt:') for value in hashes)
    assert len(set(hashes)) == 3
    assert Tools.check_password('TestBootstrapPassword!', admin.password) == (True, False)
    assert Tools.check_password('Incorrect synthetic password!', admin.password) == (False, False)
    # A real application hash outside setup still gets a fresh salt and verifies.
    fresh = Tools.get_hash('TestBootstrapPassword!')
    assert fresh.startswith('scrypt:') and fresh != admin.password
    assert Tools.check_password('TestBootstrapPassword!', fresh) == (True, False)
