from app.modules.db.db_model import PublishedServiceConfirmation


def up():
    PublishedServiceConfirmation._meta.database.create_tables([PublishedServiceConfirmation], safe=True)


def down():
    PublishedServiceConfirmation._meta.database.drop_tables([PublishedServiceConfirmation], safe=True)
