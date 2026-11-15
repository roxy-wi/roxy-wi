"""Keep Keepalived and Corosync cluster permissions independent."""
from app.modules.db import user as user_sql


SERVICE_IDS = {'keepalived': '5', 'pacemaker': '7'}


def allowed_providers(user_services: str) -> set[str]:
    """Return HA providers explicitly granted to a user."""
    granted = set(user_services.split())
    return {provider for provider, service_id in SERVICE_IDS.items() if service_id in granted}


def has_provider_access(user_id: int, provider: str) -> bool:
    """Recheck current permissions when a queued operation executes."""
    return provider in allowed_providers(user_sql.select_user_services(user_id))
