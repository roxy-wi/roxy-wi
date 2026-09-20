from playhouse.migrate import migrate, SqliteMigrator, MySQLMigrator
from peewee import SqliteDatabase

from app.modules.db.db_model import LetsEncrypt, LetsEncryptState
from app.modules.service.le import le_store


def up():
    database = LetsEncrypt._meta.database
    database.create_tables([LetsEncryptState], safe=True)
    # SAN lists can exceed VARCHAR(255), especially in MySQL.
    from peewee import TextField
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    migrate(migrator.alter_column_type('lets_encrypt', 'domains', TextField()))
    with database.atomic():
        for row in LetsEncrypt.select():
            if LetsEncryptState.get_or_none(le_id=row.id):
                continue
            import ast
            domains = ast.literal_eval(row.domains)
            state = LetsEncryptState.create(le_id=row.id, legacy_pending=True, status='migration_required',
                                             pem_name=domains[0].replace('*.', 'wildcard.') + '.pem')
            le_store.write_config(row, state, le_store.config_for(row, state))
            state.save()


def down():
    raise RuntimeError('LE rollback requires stopping workers and explicitly restoring legacy renewal jobs')
