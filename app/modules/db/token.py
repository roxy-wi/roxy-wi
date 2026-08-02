from datetime import datetime, timezone

from app.modules.db.db_model import RevokedToken


def revoke_token(jti: str, expires_at: int) -> None:
    expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc).replace(tzinfo=None)
    RevokedToken.insert(jti=jti, expires_at=expiry).on_conflict_ignore().execute()


def is_token_revoked(jti: str) -> bool:
    return RevokedToken.select().where(RevokedToken.jti == jti).exists()


def delete_expired_tokens() -> int:
    return RevokedToken.delete().where(RevokedToken.expires_at < datetime.utcnow()).execute()
