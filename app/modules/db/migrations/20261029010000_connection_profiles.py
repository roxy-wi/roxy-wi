from app.modules.db.db_model import (
    ConnectionProfile, ConnectionProfileRevision, ConnectionProfileUse,
)


def up():
    ConnectionProfile._meta.database.create_tables(
        [ConnectionProfile, ConnectionProfileRevision, ConnectionProfileUse], safe=True,
    )


def down():
    raise RuntimeError('Preserve connection profiles, credentials and pinned revisions before rollback')
