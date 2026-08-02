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
