"""Stop upgrades that would strand maintenance without a proven registration."""
from app.modules.db.db_model import HaCluster, HaMaintenancePlan, PacemakerCluster
from app.modules.operations.queue import deserialize_operation_payload


ERROR = 'Finish or recover every active HA maintenance plan through its approved return before upgrading'


def up():
    database=HaMaintenancePlan._meta.database
    if 'ha_maintenance_plans' not in database.get_tables():
        return
    busy=HaMaintenancePlan.select().where(
        HaMaintenancePlan.active_task_id.is_null(False) |
        HaMaintenancePlan.status.in_(('draining','ready','unknown','resuming','return-reviewed')))
    for plan in busy:
        try:
            payload=deserialize_operation_payload(plan.payload)
            model={'keepalived':HaCluster,'pacemaker':PacemakerCluster}.get(plan.provider)
            cluster=model.get_or_none((model.id==plan.cluster_id)&(model.group_id==plan.group_id)) if model else None
            if cluster is None or not cluster.readiness_key or payload.get('registration_key')!=cluster.readiness_key:
                raise ValueError('Unverified maintenance registration')
        except (ValueError,TypeError,AttributeError,RuntimeError):
            # Never expose decrypted fields or guess an identity for legacy plans.
            raise RuntimeError(ERROR) from None


def down():
    pass
