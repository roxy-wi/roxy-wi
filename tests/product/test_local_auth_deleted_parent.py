"""Deleting a parent between optimistic lookup and locked proof read denies safely."""
from app.modules.authentication import security
from app.modules.db.db_model import AuthenticationChallenge, User, UserSecurity


def test_deleted_parent_after_challenge_user_lookup_is_denied_without_state_recreation(product, monkeypatch):
    account = product.admin
    challenge = security.issue_challenge(account, 'regression.deleted-parent')
    original_lookup = User.get_or_none
    verified = []

    def delete_after_optimistic_lookup(*args, **kwargs):
        user = original_lookup(*args, **kwargs)
        if user is not None and user.user_id == account.user_id:
            User.delete().where(User.user_id == user.user_id).execute()
        return user

    monkeypatch.setattr(User, 'get_or_none', delete_after_optimistic_lookup)
    result = security.consume_challenge(challenge, 'regression.deleted-parent',
        verify=lambda user, payload: verified.append(user.user_id) or True)
    assert result is None
    assert verified == []
    assert not UserSecurity.select().where(UserSecurity.user_id == account.user_id).exists()
    assert not AuthenticationChallenge.select().where(AuthenticationChallenge.user_id == account.user_id).exists()
