"""An explicit method/endpoint allowlist: new API routes are denied by default."""
SCOPES = {
    'inventory.read': 'Read servers in the fixed token group',
    'services.read': 'Read service/backend and queued operation status',
    'config.read': 'Read remote configuration files and versions',
    'changes.read': 'Read configuration changes, diffs, reports and their events',
    'changes.write': 'Create, edit and validate configuration drafts',
    'changes.approve': 'Approve a change under the existing distinct-approver rules',
    'changes.deploy': 'Deploy, roll back, recover and control a change rollout',
    'services.control': 'Start, stop, reload or restart a managed service',
}
ENDPOINTS = {}


def allow(scope, method, *names):
    for name in names:
        ENDPOINTS[('api.'+name, method)] = scope


allow('inventory.read', 'GET', 'servers', 'server')
allow('services.read', 'GET', 'service__id', 'service__ip', 'service_backend__id', 'service_backend__ip', 'operation_status')
allow('config.read', 'GET', 'config_view__id', 'config_view__ip', 'config_version__id', 'config_version__ip', 'config_list', 'config_list_ip')
allow('changes.read', 'GET', 'list_config_changes', 'get_config_change', 'get_config_change_events',
      'get_config_change_audit', 'get_config_change_statistics', 'export_config_change_report', 'get_rollout_preview')
allow('changes.write', 'POST', 'create_config_change', 'validate_config_change')
allow('changes.write', 'PUT', 'update_config_change')
allow('changes.approve', 'POST', 'approve_config_change')
allow('changes.deploy', 'POST', 'deploy_config_change', 'rollback_config_change', 'cancel_config_change',
      'recover_config_change', 'pause_config_change', 'resume_config_change', 'promote_config_change',
      'run_config_change_target_action', 'schedule_config_change', 'cancel_config_change_schedule',
      'check_config_change_drift')
allow('services.control', 'POST', 'service_action__id', 'service_action__ip')
