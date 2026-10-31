from app.modules.db.db_model import PasskeyCredential, PasskeyIdentity


def up():
    PasskeyCredential._meta.database.create_tables([PasskeyIdentity, PasskeyCredential], safe=True)


def down():
    raise RuntimeError('Disable local passkey enforcement and invalidate sessions before a security rollback')
