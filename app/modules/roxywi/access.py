from app.modules.db import user as user_sql
from app.modules.roxywi.exception import RoxywiPermissionError


def ensure_group_management(actor_role: int, active_group: int, target_group: int) -> None:
    actor_role = int(actor_role)
    if actor_role == 1:
        return
    if actor_role > 2 or int(active_group) != int(target_group):
        raise RoxywiPermissionError('Cannot manage users outside the active group')


def ensure_role_assignment(actor_role: int, target_role: int) -> None:
    actor_role = int(actor_role)
    target_role = int(target_role)
    if actor_role == 1:
        return
    if actor_role > 2 or target_role == 1 or target_role < actor_role:
        raise RoxywiPermissionError('Cannot assign a role above your own role')


def ensure_target_role(actor_role: int, target_role: int) -> None:
    actor_role = int(actor_role)
    target_role = int(target_role)
    if actor_role != 1 and target_role < actor_role:
        raise RoxywiPermissionError('Cannot manage a user with a higher role')


def ensure_user_management(actor: dict, user_id: int, *, group_id: int | None = None) -> None:
    """Authorize a membership change or an account-wide mutation.

    A local role must never hide higher privileges in another group. Global
    account fields also affect every tenant sharing that account; only its
    owner or a superAdmin may change them across group boundaries.
    """
    active_group = int(actor['group_id'])
    ensure_group_management(actor['role'], active_group, group_id if group_id is not None else active_group)
    if int(actor['role']) == 1:
        return
    if group_id is None and int(user_id) == int(actor['user_id']):
        return

    user = user_sql.get_user_id(user_id)
    memberships = user_sql.select_user_groups(user_id)
    roles = [membership.user_role_id for membership in memberships]
    # Legacy role_id is not an authorization grant, but must not let an old
    # superAdmin account become editable after its memberships are changed.
    if int(user.role_id) == 1:
        roles.append(1)
    ensure_target_role(actor['role'], min(roles, default=4))

    if group_id is None:
        if (not memberships or int(user.group_id) != active_group
                or any(membership.user_group_id != active_group for membership in memberships)):
            raise RoxywiPermissionError('Only a superAdmin can manage accounts shared across groups')
