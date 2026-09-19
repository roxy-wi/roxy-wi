from app.modules.common.time import utc_now
from app.modules.db.db_model import Backup, S3Backup, BackupSchedule
from app.modules.service.backup_scheduler import next_run, schedule_timezone


def up():
    BackupSchedule._meta.database.create_tables([BackupSchedule], safe=True)
    zone = schedule_timezone()
    for kind, model in (('fs', Backup), ('s3', S3Backup)):
        for config in model.select():
            BackupSchedule.get_or_create(kind=kind, backup_id=config.id, defaults={
                'timezone': zone, 'next_run_at': next_run(config.time, zone, utc_now()),
                'legacy_pending': True,
            })


def down():
    raise RuntimeError('Backup rollback requires stopping workers and restoring legacy cron explicitly')
