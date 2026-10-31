from app.modules.db.db_model import TotpCredential


def up():
    TotpCredential._meta.database.create_tables([TotpCredential], safe=True)


def down():
    raise RuntimeError('Removing active MFA is not a safe rollback')
