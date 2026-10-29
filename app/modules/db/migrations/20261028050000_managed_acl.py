from app.modules.db.db_model import ManagedAclFeed,ManagedAclVersion


def up():
    ManagedAclFeed._meta.database.create_tables([ManagedAclFeed,ManagedAclVersion],safe=True)


def down():
    ManagedAclFeed._meta.database.drop_tables([ManagedAclVersion,ManagedAclFeed],safe=True)
