"""RFC 6238 using PyOTP; no external service or subscription is consulted."""
import hmac
import re
import pyotp
from peewee import SqliteDatabase
from app.modules.db.db_model import TotpCredential
from app.modules.server.ssh import crypt_password, decrypt_password
from app.modules.authentication import security


def has_factor(user_id, *, locking=True):
    query = TotpCredential.select().where(TotpCredential.user_id == user_id)
    database = TotpCredential._meta.database
    if locking and database.in_transaction() and not isinstance(database, SqliteDatabase):
        query = query.for_update()
    return query.first() is not None


def match_counter(secret, code):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
        return None
    counter = security.now() // 30
    generator = pyotp.TOTP(secret, digits=6, interval=30)
    for candidate in (counter, counter - 1, counter + 1):
        if hmac.compare_digest(generator.at(candidate * 30), code):
            return candidate
    return None


def verify_factor(user, data):
    row = TotpCredential.get_or_none(TotpCredential.user_id == user.user_id)
    if not row:
        return False
    counter = match_counter(decrypt_password(row.secret_encrypted), data.get('otp'))
    if counter is None:
        return False
    return bool(TotpCredential.update(last_counter=counter).where(
        (TotpCredential.user_id == user.user_id) & (TotpCredential.last_counter < counter)).execute())


def setup_payload(user):
    secret = pyotp.random_base32()
    return dict(secret=secret, uri=pyotp.TOTP(secret).provisioning_uri(user.username, issuer_name='Roxy-WI'))


def activate(user, payload, code):
    replacing = has_factor(user.user_id)
    if replacing and not payload.get('replace'):
        return False
    counter = match_counter(payload['secret'], code)
    if counter is None:
        return False
    values = dict(secret_encrypted=crypt_password(payload['secret']).decode('ascii'),
                  last_counter=counter, created_at=security.now())
    if replacing:
        TotpCredential.update(**values).where(TotpCredential.user_id == user.user_id).execute()
    else:
        TotpCredential.create(user_id=user.user_id, **values)
    return True


def reset(user_id):
    TotpCredential.delete().where(TotpCredential.user_id == user_id).execute()


def rotate_encrypted_state(old_fernet, new_fernet):
    from cryptography.fernet import InvalidToken
    count = 0
    for row in TotpCredential.select():
        token = row.secret_encrypted.encode('ascii')
        try:
            plaintext = old_fernet.decrypt(token)
        except InvalidToken:
            new_fernet.decrypt(token)
            continue
        TotpCredential.update(secret_encrypted=new_fernet.encrypt(plaintext).decode('ascii')).where(
            TotpCredential.user_id == row.user_id).execute()
        count += 1
    return count
