import uuid

import pytest

import app.modules.db.server as server_sql
import app.modules.db.smon as smon_sql
import app.modules.db.backup as backup_sql
import app.modules.db.add as add_sql
from app.modules.db.db_model import Backup, Groups, Option, Server, SMON
from app.modules.roxywi.exception import RoxywiResourceNotFound


@pytest.mark.security
def test_server_list_does_not_treat_group_one_as_global_access():
    suffix = uuid.uuid4().hex
    other_group = Groups.create(name=f'tenant-{suffix}', description='test tenant')
    own_server = Server.create(hostname=f'own-{suffix}', ip=f'192.0.2.{int(suffix[:2], 16) % 200 + 1}', group_id='1')
    foreign_server = Server.create(hostname=f'foreign-{suffix}', ip=f'198.51.100.{int(suffix[2:4], 16) % 200 + 1}', group_id=str(other_group.group_id))

    visible_ids = {server[0] for server in server_sql.get_dick_permit(1, disable=0, virt=True)}

    assert own_server.server_id in visible_ids
    assert foreign_server.server_id not in visible_ids


@pytest.mark.security
def test_smon_list_is_always_scoped_to_requested_group():
    suffix = uuid.uuid4().hex
    other_group = Groups.create(name=f'smon-tenant-{suffix}', description='test tenant')
    own_check = SMON.create(name=f'own-check-{suffix}', port=10001, http='', body='', user_group=1)
    foreign_check = SMON.create(
        name=f'foreign-check-{suffix}', port=10002, http='', body='', user_group=other_group.group_id
    )

    visible_ids = {check.id for check in smon_sql.smon_list(1)}

    assert own_check.id in visible_ids
    assert foreign_check.id not in visible_ids


@pytest.mark.security
def test_backup_list_is_scoped_through_its_server_group():
    suffix = uuid.uuid4().hex
    other_group = Groups.create(name=f'backup-tenant-{suffix}', description='test tenant')
    own_server = Server.create(hostname=f'own-backup-{suffix}', ip=f'203.0.113.{int(suffix[:2], 16) % 200 + 1}', group_id='1')
    foreign_server = Server.create(
        hostname=f'foreign-backup-{suffix}', ip=f'100.64.0.{int(suffix[2:4], 16) % 200 + 1}',
        group_id=str(other_group.group_id)
    )
    own_backup = Backup.create(
        server_id=str(own_server.server_id), rserver='backup.example', rpath='/backup', type='backup',
        time='daily', cred_id=1
    )
    foreign_backup = Backup.create(
        server_id=str(foreign_server.server_id), rserver='backup.example', rpath='/backup', type='backup',
        time='daily', cred_id=1
    )

    visible_ids = {backup.id for backup in backup_sql.select_backups(group_id=1)}

    assert own_backup.id in visible_ids
    assert foreign_backup.id not in visible_ids


@pytest.mark.security
def test_saved_option_cannot_be_changed_from_another_group():
    suffix = uuid.uuid4().hex
    other_group = Groups.create(name=f'option-tenant-{suffix}', description='test tenant')
    option = Option.create(options=f'foreign-{suffix}', groups=str(other_group.group_id))

    with pytest.raises(RoxywiResourceNotFound):
        add_sql.update_options('stolen', option.id, 1)
    with pytest.raises(RoxywiResourceNotFound):
        add_sql.delete_option(option.id, 1)

    assert Option.get_by_id(option.id).options == f'foreign-{suffix}'
