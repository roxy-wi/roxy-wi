from peewee import MySQLDatabase
from app.modules.db.db_model import ManagedAclFeed,ManagedAclVersion


def test_mysql_ddl_does_not_truncate_encrypted_large_feeds_and_reviews():
    database=MySQLDatabase('ddl_only_no_connection')
    with database.bind_ctx([ManagedAclFeed,ManagedAclVersion],bind_refs=False,bind_backrefs=False):
        feed_sql,_=ManagedAclFeed._schema._create_table().query()
        version_sql,_=ManagedAclVersion._schema._create_table().query()
        assert '`configuration` LONGTEXT' in feed_sql
        assert '`content` LONGTEXT' in version_sql and '`details` LONGTEXT' in version_sql
