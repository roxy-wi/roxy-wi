from app.modules.db.db_model import PersonalAccessToken, PersonalTokenGate


def up():
    PersonalAccessToken._meta.database.create_tables([PersonalAccessToken, PersonalTokenGate], safe=True)


def down():
    raise RuntimeError('Revoke and preserve personal token metadata before rollback')
