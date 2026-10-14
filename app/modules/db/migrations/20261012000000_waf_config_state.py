from app.modules.db.db_model import WafConfigState


def up():
    WafConfigState._meta.database.create_tables([WafConfigState], safe=True)


def down():
    WafConfigState._meta.database.drop_tables([WafConfigState], safe=True)
