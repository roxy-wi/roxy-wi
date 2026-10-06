import hashlib
import posixpath

from peewee import SqliteDatabase
from playhouse.migrate import MySQLMigrator, migrate

from app.modules.db.db_model import HaproxySection, Server, Setting


def up():
    database = HaproxySection._meta.database
    # Remove the unreleased, group-wide preview setting. Sources are discovered
    # from each service's startup configuration; the opt-in flag is per server.
    Setting.delete().where(Setting.param == 'haproxy_config_args').execute()
    columns = {column.name for column in database.get_columns('haproxy_sections')}
    indexes = database.get_indexes('haproxy_sections')
    current_unique = any(index.unique and index.columns == ['server_id', 'type', 'name', 'file_id'] for index in indexes)
    old_unique = any(index.unique and index.columns == ['server_id', 'type', 'name'] for index in indexes)
    if 'file_id' in columns and current_unique and not old_unique:
        return

    def identities():
        paths = {str(row.group_id): row.value for row in Setting.select().where(Setting.param == 'haproxy_config_path')}
        groups = {row.server_id: str(row.group_id) for row in Server.select()}
        extra = ', config_path, file_id' if {'config_path', 'file_id'} <= columns else ''
        for row in database.execute_sql('SELECT id, server_id, type, name, config' + extra + ' FROM haproxy_sections').fetchall():
            if extra and row[6]:
                yield row
                continue
            path = posixpath.normpath(paths.get(groups[row[1]]) or '/etc/haproxy/haproxy.cfg')
            yield (*row[:5], path, hashlib.sha256(path.encode()).hexdigest())

    values = list(identities())
    if isinstance(database, SqliteDatabase):
        # The old UNIQUE constraint has an SQLite autoindex that cannot be dropped.
        class Replacement(HaproxySection):
            class Meta:
                table_name = 'haproxy_sections_file_migration'
        with database.atomic():
            Replacement.create_table()
            for row in values:
                database.execute_sql(
                    'INSERT INTO haproxy_sections_file_migration '
                    '(id, server_id, type, name, config, config_path, file_id) VALUES (?, ?, ?, ?, ?, ?, ?)', row)
            database.execute_sql('DROP TABLE haproxy_sections')
            database.execute_sql('ALTER TABLE haproxy_sections_file_migration RENAME TO haproxy_sections')
    else:
        migrator = MySQLMigrator(database)
        for name in ('config_path', 'file_id'):
            if name not in columns:
                migrate(migrator.add_column('haproxy_sections', name, HaproxySection._meta.fields[name]))
        for row in values:
            database.execute_sql('UPDATE haproxy_sections SET config_path=%s, file_id=%s WHERE id=%s',
                                 (row[5], row[6], row[0]))
        if not current_unique:
            migrate(migrator.add_index('haproxy_sections', ('server_id', 'type', 'name', 'file_id'), True))
        for index in database.get_indexes('haproxy_sections'):
            if index.unique and index.columns == ['server_id', 'type', 'name']:
                migrate(migrator.drop_index('haproxy_sections', index.name))


def down():
    raise RuntimeError('File-aware HAProxy sections cannot be merged into main-file identities safely')
