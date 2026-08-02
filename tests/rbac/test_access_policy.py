import pytest

from app.modules.roxywi.access import (
    ensure_group_management,
    ensure_role_assignment,
    ensure_target_role,
)
from app.modules.roxywi.exception import RoxywiPermissionError


@pytest.mark.rbac
def test_group_admin_cannot_manage_another_group():
    with pytest.raises(RoxywiPermissionError):
        ensure_group_management(actor_role=2, active_group=10, target_group=11)


@pytest.mark.rbac
def test_group_admin_cannot_grant_superadmin():
    with pytest.raises(RoxywiPermissionError):
        ensure_role_assignment(actor_role=2, target_role=1)


@pytest.mark.rbac
def test_group_admin_can_grant_equal_or_lower_privileges():
    ensure_role_assignment(actor_role=2, target_role=2)
    ensure_role_assignment(actor_role=2, target_role=4)


@pytest.mark.rbac
def test_admin_cannot_manage_higher_privileged_user():
    with pytest.raises(RoxywiPermissionError):
        ensure_target_role(actor_role=2, target_role=1)
