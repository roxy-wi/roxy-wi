import importlib.util
import json
import re
import secrets
from datetime import datetime

from peewee import IntegrityError, SqliteDatabase, fn

from app.modules.db import oidc as oidc_sql
from app.modules.db.db_model import OidcIdentity, User, UserGroups
import app.modules.db.user as user_sql
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.oidc.errors import OidcLoginError
from app.modules.subscription.access import OIDC, require_feature


def extract_claim(claims: dict, claim_name: str, default=None):
    """Extract either a direct claim or a dotted nested claim."""
    if not claims or not claim_name:
        return default
    if claim_name in claims:
        return claims.get(claim_name)

    current = claims
    for part in str(claim_name).split('.'):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def normalize_groups(value) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith('['):
            try:
                return normalize_groups(json.loads(value))
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _claim_to_string(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if value in (None, ''):
        return None
    return str(value).strip()


def _provider_domains(provider) -> list[str]:
    if not provider.allowed_domains:
        return []
    try:
        domains = json.loads(provider.allowed_domains)
    except (TypeError, json.JSONDecodeError):
        domains = str(provider.allowed_domains).split(',')
    return [str(domain).strip().lower() for domain in domains if str(domain).strip()]


def _validate_provider_policy(provider, claims: dict, email: str) -> None:
    allowed_domains = _provider_domains(provider)
    if allowed_domains:
        domain = email.rsplit('@', 1)[1].lower() if email and '@' in email else None
        if not domain or domain not in allowed_domains:
            raise OidcLoginError(
                'oidc_domain_denied',
                'This email domain is not allowed for this OIDC provider',
                403,
            )

    if provider.require_verified_email:
        if not email:
            raise OidcLoginError(
                'oidc_email_missing',
                f"OIDC email claim '{provider.email_claim}' was not found",
                403,
            )
        verified = extract_claim(claims, 'email_verified')
        if str(verified).lower() not in ('true', '1', 'yes'):
            raise OidcLoginError(
                'oidc_email_not_verified',
                'OIDC provider did not confirm that email is verified',
                403,
            )


def _safe_username(value: str) -> str:
    value = str(value or '').strip().lower()
    value = re.sub(r'[^a-z0-9_.-]+', '-', value).strip('.-_')
    return value or 'oidc-user'


def _unique_username(value: str) -> str:
    base = _safe_username(value)
    candidate = base
    counter = 2
    while User.get_or_none(fn.LOWER(User.username) == candidate.casefold()):
        candidate = f'{base}-{counter}'
        counter += 1
    return candidate


def _current(query):
    # Locking reads see the latest committed row under MySQL REPEATABLE READ.
    database = User._meta.database
    if database.in_transaction() and not isinstance(database, SqliteDatabase):
        query = query.for_update()
    return query


def _locked_user(user_id):
    return _current(User.select().where(User.user_id == user_id)).first()


def _mapping_changed():
    return OidcLoginError('oidc_identity_changed',
                          'Local account mapping changed; sign in again', 403)


def _security_provider():
    # OIDC also works in installations without the optional local MFA package.
    try:
        available = importlib.util.find_spec('app.modules.authentication.security')
    except ModuleNotFoundError as error:
        if error.name != 'app.modules.authentication':
            raise
        return None
    if available is None:
        return None
    from app.modules.authentication import security
    return security


def _find_user_by_email(email: str):
    if not email:
        return None
    matches = list(User.select().where(fn.LOWER(User.email) == email.casefold()).limit(2))
    if len(matches) > 1:
        raise OidcLoginError(
            'oidc_email_ambiguous',
            'More than one local user has this email address',
            409,
        )
    return matches[0] if matches else None


def _create_local_user(provider, subject: str, email: str, username: str):
    if not email:
        raise OidcLoginError(
            'oidc_email_missing',
            'An email claim is required to create a Roxy-WI user',
            403,
        )

    local_username = _unique_username(username or email.split('@', 1)[0] or subject)
    return User.create(
        username=local_username,
        email=email,
        password=roxy_wi_tools.Tools.get_hash(secrets.token_urlsafe(48)),
        role_id=str(provider.default_role_id),
        group_id=str(provider.default_group_id),
        ldap_user=0,
        enabled=1,
    )


def _resolve_user(provider, claims: dict):
    subject = _claim_to_string(extract_claim(claims, provider.subject_claim))
    if not subject:
        raise OidcLoginError(
            'oidc_subject_missing',
            f"OIDC subject claim '{provider.subject_claim}' was not found",
            400,
        )

    issuer = _claim_to_string(extract_claim(claims, 'iss')) or provider.issuer
    if not issuer:
        raise OidcLoginError(
            'oidc_issuer_missing',
            'OIDC issuer claim was not found',
            400,
        )

    email = _claim_to_string(extract_claim(claims, provider.email_claim))
    username = _claim_to_string(extract_claim(claims, provider.username_claim))
    _validate_provider_policy(provider, claims, email)

    identity = OidcIdentity.get_or_none(
        (OidcIdentity.issuer == issuer) & (OidcIdentity.subject == subject)
    )
    if identity:
        # The first identity read identifies the parent to lock, not a principal.
        # Recheck the exact mapping after that lock before updating any child row.
        user = _locked_user(identity.user_id)
        identity = _current(OidcIdentity.select().where(
            (OidcIdentity.id == identity.id) & (OidcIdentity.issuer == issuer) &
            (OidcIdentity.subject == subject) & (OidcIdentity.user_id == identity.user_id)
        )).first()
        if user is None or identity is None:
            raise _mapping_changed()
        if not user.enabled:
            raise OidcLoginError('oidc_user_disabled', 'Linked local user is disabled', 403)
        identity.email = email
        identity.username = username
        identity.raw_claims = json.dumps(claims, default=str)
        identity.last_login_at = datetime.now()
        identity.save()
        return user, False

    email_user = _find_user_by_email(email)
    user = email_user if provider.auto_link_by_email else None
    if user:
        user = _locked_user(user.user_id)
        if user is None or not user.email or user.email.casefold() != email.casefold():
            raise _mapping_changed()
    if user and not user.enabled:
        raise OidcLoginError('oidc_user_disabled', 'Local user with this email is disabled', 403)

    if email_user and not provider.auto_link_by_email:
        raise OidcLoginError(
            'oidc_email_already_exists',
            'A local user with this email already exists and automatic linking is disabled',
            409,
        )

    created = False
    if not user:
        if not provider.auto_create_users:
            raise OidcLoginError(
                'oidc_user_not_found',
                'No linked local user was found and auto-create is disabled',
                403,
            )
        user = _create_local_user(provider, subject, email, username)
        created = True

    try:
        OidcIdentity.create(
            provider_id=provider.id,
            user_id=user.user_id,
            issuer=issuer,
            subject=subject,
            email=email,
            username=username,
            raw_claims=json.dumps(claims, default=str),
            last_login_at=datetime.now(),
        )
    except IntegrityError:
        # Another login linked this subject. Do not switch parents while holding
        # the candidate account lock; retry from a fresh verified mapping.
        raise _mapping_changed() from None

    return user, created


def _active_memberships(user_id: int) -> list[int]:
    return [
        int(membership.user_group_id)
        for membership in _current(UserGroups.select().where(UserGroups.user_id == user_id))
    ]


def _sync_group_memberships(provider, user, claims: dict, created: bool) -> None:
    mappings = list(oidc_sql.list_mappings(provider.id, active_only=True))

    if provider.sync_group_memberships and mappings:
        external_groups = {
            item.casefold()
            for item in normalize_groups(extract_claim(claims, provider.groups_claim))
            if item
        }
        matched_group_ids = []
        mapped_group_ids = []

        for mapping in mappings:
            mapped_group_ids.append(mapping.group_id)
            if mapping.external_group.strip().casefold() not in external_groups:
                continue
            user_sql.update_user_role(user.user_id, mapping.group_id, mapping.role_id)
            matched_group_ids.append(mapping.group_id)

        if provider.remove_missing_group_memberships:
            query = (
                (UserGroups.user_id == user.user_id)
                & (UserGroups.user_group_id.in_(mapped_group_ids))
            )
            if matched_group_ids:
                query &= ~(UserGroups.user_group_id.in_(matched_group_ids))
            UserGroups.delete().where(query).execute()

        memberships = _active_memberships(user.user_id)
        if not memberships:
            raise OidcLoginError(
                'oidc_group_mapping_not_matched',
                'OIDC login did not assign any Roxy-WI group. Check the groups claim and mappings.',
                403,
            )
    else:
        memberships = _active_memberships(user.user_id)
        if created and provider.default_group_id not in memberships:
            user_sql.update_user_role(user.user_id, provider.default_group_id, provider.default_role_id)
            memberships.append(provider.default_group_id)

        if not memberships:
            raise OidcLoginError(
                'oidc_user_has_no_group',
                'The linked Roxy-WI user does not belong to an active group',
                403,
            )

    if int(user.group_id) not in memberships:
        user_sql.update_user_current_groups(memberships[0], user.user_id)
        user.group_id = str(memberships[0])


def complete_oidc_login(provider, claims: dict):
    """Resolve an OIDC identity and return local JWT parameters."""
    require_feature(OIDC)
    database = User._meta.database
    security = _security_provider()
    with security.atomic() if security else database.atomic():
        user, created = _resolve_user(provider, claims)
        if security:
            user, expected = security.capture_account(user.user_id)
        _sync_group_memberships(provider, user, claims, created)
        user = _locked_user(user.user_id)
        if user is None or not user.enabled:
            raise _mapping_changed()
        result = {
            'group': str(user.group_id),
            'user': user.user_id,
            'name': user.username,
        }
        if security:
            result.update(security.login_proof(user, 'oidc', expected=expected))
        return result
