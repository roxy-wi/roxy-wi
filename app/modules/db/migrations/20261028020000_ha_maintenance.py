from app.modules.db.db_model import HaMaintenancePlan


def up():
    HaMaintenancePlan._meta.database.create_tables([HaMaintenancePlan],safe=True)


def down():
    HaMaintenancePlan._meta.database.drop_tables([HaMaintenancePlan],safe=True)
