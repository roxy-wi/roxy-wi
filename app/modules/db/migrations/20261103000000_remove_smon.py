"""Remove the retired SMON schema and its application settings."""
from app.modules.db.db_model import Alerts, RoxyTool, Setting, WorkerRun, WorkerState


def up() -> None:
    """Drop dependent tables first and make repeated execution safe."""
    database = RoxyTool._meta.database
    for table in (
        'smon_status_page_checks', 'smon_status_pages', 'smon_history',
        'smon_tcp_check', 'smon_http_check', 'smon_ping_check', 'smon_dns_check',
        'smon_agents', 'smon',
    ):
        database.execute_sql(f'DROP TABLE IF EXISTS {table}')
    with database.atomic():
        RoxyTool.delete().where(RoxyTool.name == 'roxy-wi-smon').execute()
        Setting.delete().where(Setting.section == 'smon').execute()
        for model in (WorkerState, WorkerRun):
            if model.table_exists():
                model.delete().where(model.service == 'smon').execute()
        if Alerts.table_exists():
            Alerts.delete().where(Alerts.service == 'SMON').execute()


def down() -> None:
    """Removed monitoring data can only be recovered from a database backup."""
    raise RuntimeError('Restore the database backup to recover SMON data')
