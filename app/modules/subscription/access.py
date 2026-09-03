from dataclasses import dataclass
from functools import wraps
from types import MappingProxyType
from typing import Iterable, Optional

from flask import jsonify, request

import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi.exception import RoxywiPermissionError


OIDC = 'oidc'
CHANGE_CENTER = 'change_center'
GIT_BACKUP = 'git_backup'
SMON_STATUS_PAGES = 'smon_status_pages'
MANAGED_SERVICES = 'managed_services'

# Package/systemd names accepted by the local installation controls.  Both
# keep-alive spellings exist in older packages and must be covered.
MANAGED_SERVICE_TOOLS = frozenset({
    'roxy-wi-checker',
    'roxy-wi-keep_alive',
    'roxy-wi-keep-alive',
    'roxy-wi-metrics',
    'roxy-wi-portscanner',
    'roxy-wi-prometheus-exporter',
    'roxy-wi-smon',
    'roxy-wi-socket',
})


@dataclass(frozen=True)
class FeaturePolicy:
    allowed_plans: frozenset[str]
    error: str


FEATURE_POLICIES = MappingProxyType({
    OIDC: FeaturePolicy(
        frozenset({'company', 'cloud', 'support'}),
        'OIDC requires an active Company plan or higher',
    ),
    CHANGE_CENTER: FeaturePolicy(
        frozenset({'support'}),
        'Change Center requires an active Premium plan',
    ),
    GIT_BACKUP: FeaturePolicy(
        frozenset({'support'}),
        'Git backup requires an active Premium plan',
    ),
    SMON_STATUS_PAGES: FeaturePolicy(
        frozenset({'support'}),
        'SMON status pages require an active Premium plan',
    ),
    MANAGED_SERVICES: FeaturePolicy(
        frozenset({'user', 'company', 'cloud', 'support'}),
        'Additional services require an active User plan or higher',
    ),
})


@dataclass(frozen=True)
class SubscriptionEntitlement:
    active: bool
    plan: str


def _policy(feature: str) -> FeaturePolicy:
    try:
        return FEATURE_POLICIES[feature]
    except KeyError as exc:
        raise ValueError(f'Unknown subscription feature: {feature}') from exc


def normalize_subscription(subscription: Optional[dict] = None) -> SubscriptionEntitlement:
    if subscription is None:
        subscription = roxywi_common.return_user_subscription()

    try:
        active = int(subscription.get('user_status', 0)) == 1
        plan = str(subscription.get('user_plan') or '').strip().lower()
    except (AttributeError, TypeError, ValueError):
        return SubscriptionEntitlement(active=False, plan='')
    return SubscriptionEntitlement(active=active, plan=plan)


def is_feature_available(feature: str, subscription: Optional[dict] = None) -> bool:
    policy = _policy(feature)
    entitlement = normalize_subscription(subscription)
    return entitlement.active and entitlement.plan in policy.allowed_plans


def require_feature(feature: str, subscription: Optional[dict] = None) -> SubscriptionEntitlement:
    policy = _policy(feature)
    entitlement = normalize_subscription(subscription)
    if not entitlement.active or entitlement.plan not in policy.allowed_plans:
        raise RoxywiPermissionError(policy.error)
    return entitlement


def feature_required(feature: str, *, methods: Optional[Iterable[str]] = None):
    policy = _policy(feature)
    guarded_methods = frozenset(method.upper() for method in methods) if methods else None

    def decorator(function):
        @wraps(function)
        def decorated_view(*args, **kwargs):
            if guarded_methods is not None and request.method.upper() not in guarded_methods:
                return function(*args, **kwargs)
            try:
                require_feature(feature)
            except RoxywiPermissionError:
                return jsonify({'status': 'failed', 'error': policy.error}), 403
            return function(*args, **kwargs)

        return decorated_view

    return decorator
