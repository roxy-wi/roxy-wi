import uuid

import pytest
from cryptography.fernet import Fernet

from app.modules.db.db_model import Cred
from rotate_credential_secret import rotate_credentials


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
    monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE', old_key.decode('ascii'))
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', new_key.decode('ascii'))

    assert rotate_credentials() >= 1

    credential = Cred.get_by_id(credential.id)
    assert Fernet(new_key).decrypt(credential.password.encode('ascii')) == b'secret-password'
