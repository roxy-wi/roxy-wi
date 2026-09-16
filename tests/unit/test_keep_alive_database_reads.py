import pytest
from peewee import SqliteDatabase

from app.modules.db import keep_alive
from app.modules.db.db_model import Server


@pytest.mark.parametrize('selector,flag', [
    (keep_alive.select_keep_alive, 'haproxy_active'),
    (keep_alive.select_nginx_keep_alive, 'nginx_active'),
    (keep_alive.select_apache_keep_alive, 'apache_active'),
    (keep_alive.select_keepalived_keep_alive, 'keepalived_active'),
])
def test_waiting_between_server_checks_does_not_pin_wal(tmp_path, selector, flag):
    path = tmp_path / 'keep-alive.db'
    reader = SqliteDatabase(path, pragmas={'journal_mode': 'wal', 'wal_autocheckpoint': 0})
    writer = SqliteDatabase(path, pragmas={'journal_mode': 'wal', 'wal_autocheckpoint': 0})
    with reader.bind_ctx([Server], bind_refs=False, bind_backrefs=False):
        try:
            reader.create_tables([Server])
            for index in range(3):
                Server.create(hostname=f'target-{index}', ip=f'192.0.2.{index + 1}', group_id='1', **{flag: 1})
            Server.create(hostname='disabled', ip='192.0.2.4', group_id='1')
            reader.execute_sql('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()

            targets = selector()
            iterator = iter(targets)
            first = next(iterator)
            assert first.ip == '192.0.2.1'
            if flag == 'keepalived_active':
                assert first.port == 22

            # The caller retains its iterator while doing slow SSH/TCP work;
            # another connection must still be able to checkpoint new writes.
            writer.execute_sql('UPDATE servers SET description = ?', ('updated during network check',))
            busy, frames, checkpointed = writer.execute_sql('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
            assert busy == 0
            assert frames > 0
            assert checkpointed == frames
            assert len(list(iterator)) == 2
        finally:
            writer.close()
            reader.close()
