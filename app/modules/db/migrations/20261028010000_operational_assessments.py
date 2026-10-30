from app.modules.db.db_model import OperationalAssessment, HaReadinessProfile


def up():
    OperationalAssessment._meta.database.create_tables([OperationalAssessment, HaReadinessProfile], safe=True)


def down():
    OperationalAssessment._meta.database.drop_tables([HaReadinessProfile, OperationalAssessment], safe=True)
