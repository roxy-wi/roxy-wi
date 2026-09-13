import os
import shutil
import datetime

from app import scheduler
import app.modules.db.sql as sql
import app.modules.db.roxy as roxy_sql
import app.modules.db.history as history_sql
import app.modules.roxywi.roxy as roxy
import app.modules.common.common as common
import app.modules.tools.common as tools_common
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.db.db_model import close_database_connection

get_config = roxy_wi_tools.GetConfigVar()


def _run_database_job(callback):
    """Run a scheduler callback and release its thread-local DB connection."""
    try:
        with scheduler.app.app_context():
            return callback()
    finally:
        close_database_connection()


def update_new_versions() -> None:
    tools = roxy_sql.get_roxy_tools()
    for tool in tools:
        ver = roxy.check_new_version(tool)
        roxy_sql.update_tool_new_version(tool, ver)

    app_ver = roxy.check_new_version('roxy-wi')
    roxy_sql.update_app_versions(roxy.check_ver(), app_ver)


@scheduler.task('interval', id='update_plan', minutes=55, misfire_grace_time=None)
def update_user_status():
    return _run_database_job(roxy.update_plan)


@scheduler.task('interval', id='check_new_version', days=1, misfire_grace_time=None)
def check_new_version():
    return _run_database_job(update_new_versions)


@scheduler.task('interval', id='update_cur_tool_versions', days=1, misfire_grace_time=None)
def update_cur_tool_versions():
    return _run_database_job(tools_common.update_cur_tool_versions)


@scheduler.task('interval', id='delete_action_history_for_period', minutes=70, misfire_grace_time=None)
def delete_action_history_for_period():
    return _run_database_job(history_sql.delete_action_history_for_period)


@scheduler.task('interval', id='delete_old_logs', hours=1, misfire_grace_time=None)
def delete_old_logs():
    def delete_logs():
        time_storage = sql.get_setting('log_time_storage')
        log_path = get_config.get_config_var('main', 'log_path')
        try:
            time_storage_hours = time_storage * 24
            for dirpath, dirnames, filenames in os.walk(log_path):
                for file in filenames:
                    curpath = os.path.join(dirpath, file)
                    file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
                    if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
                        os.remove(curpath)
        except Exception as e:
            print(f'error: cannot delete old log files: {e}')
    return _run_database_job(delete_logs)


@scheduler.task('interval', id='update_owner_on_log', hours=12, misfire_grace_time=None)
def update_owner_on_log():
    if get_config.get_config_var('main', 'deployment_mode', 'package').lower() != 'package':
        return
    log_path = get_config.get_config_var('main', 'log_path')
    try:
        common.set_correct_owner(log_path)
    except Exception:
        pass


@scheduler.task(
    'interval',
    id='change_center_scheduled_deployments',
    seconds=15,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
def run_change_center_scheduled_deployments():
    """Run due Change Center deployments from the dedicated scheduler process."""
    def run():
        from app.modules.change import automation
        return automation.run_due_scheduled_changes()
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='change_center_deliveries',
    seconds=10,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
def run_change_center_deliveries():
    """Deliver queued notifications and webhooks without blocking deployments."""
    def run():
        from app.modules.change import automation
        return automation.process_pending_deliveries()
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='service_event_deliveries',
    seconds=10,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
def run_service_event_deliveries():
    """Retry notifications created by independently deployed services."""
    def run():
        from app.modules.integrations.service_events import deliver_pending_notifications
        return deliver_pending_notifications()
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='service_integration_retention',
    hours=24,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=300,
)
def run_service_integration_retention():
    """Apply existing Checker history retention to distributed service data."""
    def run():
        from app.modules.db.service_event import prune_service_events, prune_worker_states
        from app.modules.db.portscanner import delete_portscanner_history
        retention_days = int(sql.get_setting('checker_keep_history_range') or 14)
        portscanner_retention_days = int(sql.get_setting('portscanner_keep_history_range') or 14)
        history_sql.delete_alert_history(retention_days, 'Checker')
        delete_portscanner_history(portscanner_retention_days)
        deleted_events = prune_service_events(retention_days)
        deleted_workers = prune_worker_states()
        return deleted_events + deleted_workers
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='service_command_outbox',
    seconds=5,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
def run_service_command_outbox():
    """Publish desired-state commands created by the Roxy-WI API."""
    def run():
        from app.modules.integrations.service_commands import publish_pending_commands
        return publish_pending_commands()
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='operation_outbox',
    seconds=5,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
def run_operation_outbox():
    """Publish durable SSH/Ansible operations for package and container workers."""
    def run():
        from app.modules.operations.queue import publish_pending_operations
        return publish_pending_operations()
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='service_assignment_reconciliation',
    minutes=1,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=30,
)
def run_service_assignment_reconciliation():
    """Reconcile existing worker settings with distributed desired state."""
    def run():
        from app.modules.db.service_command import (
            reconcile_checker_assignments,
            reconcile_checker_udp_assignments,
            reconcile_metrics_assignments,
            reconcile_portscanner_assignments,
        )
        return (
            reconcile_checker_assignments()
            + reconcile_checker_udp_assignments()
            + reconcile_metrics_assignments()
            + reconcile_portscanner_assignments()
        )
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='delete_old_service_metrics',
    hours=24,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=300,
)
def delete_old_service_metrics():
    """Retain the legacy three-day graph window after removing metrics_master."""
    def run():
        from app.modules.db.metric import delete_service_metrics
        for service in ('haproxy', 'http', 'nginx', 'apache', 'waf'):
            delete_service_metrics(service)
    return _run_database_job(run)


@scheduler.task(
    'interval',
    id='change_center_drift_detection',
    minutes=5,
    max_instances=1,
    coalesce=True,
    misfire_grace_time=60,
)
def run_change_center_drift_detection():
    """Continuously compare deployed configurations with approved baselines."""
    def run():
        from app.modules.change import automation
        return automation.run_continuous_drift_scan()
    return _run_database_job(run)


@scheduler.task('interval', id='delete_ansible_artifacts', hours=24, misfire_grace_time=None)
def delete_ansible_artifacts():
    lib_path = get_config.get_config_var('main', 'lib_path')
    ansible_path = get_config.get_config_var(
        'ansible', 'private_data_dir', f'{lib_path}/ansible'
    )
    folders = ['artifacts', 'env']

    for folder in folders:
        if os.path.isdir(f'{ansible_path}/{folder}'):
            try:
                shutil.rmtree(f'{ansible_path}/{folder}')
            except Exception as e:
                raise Exception(f'error: Cron cannot delete ansible folders: {e}')
