from app.modules.db.db_model import Backup, S3Backup, GitSetting
from app.modules.db.common import out_error


def insert_backup_job(server, rserver, rpath, backup_type, time, cred, description):
	try:
		Backup.insert(
			server=server, rhost=rserver, rpath=rpath, backup_type=backup_type, time=time,
			cred=cred, description=description
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_s3_backup_job(server, s3_server, bucket, secret_key, access_key, time, description):
	try:
		S3Backup.insert(
			server=server, s3_server=s3_server, bucket=bucket, secret_key=secret_key, access_key=access_key, time=time,
			description=description
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_backup(server, rserver, rpath, backup_type, time, cred, description, backup_id):
	backup_update = Backup.update(
		server=server, rhost=rserver, rpath=rpath, backup_type=backup_type, time=time,
		cred=cred, description=description
	).where(Backup.id == backup_id)
	try:
		backup_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_backups(backup_id: int) -> bool:
	query = Backup.delete().where(Backup.id == backup_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_s3_backups(backup_id: int) -> bool:
	query = S3Backup.delete().where(S3Backup.id == backup_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_git(server_id, service_id, repo, branch, period, cred, description):
	try:
		GitSetting.insert(
			server_id=server_id, service_id=service_id, repo=repo, branch=branch, period=period,
			cred_id=cred, description=description
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_git(git_id):
	query = GitSetting.delete().where(GitSetting.id == git_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_gits(**kwargs):
	if kwargs.get("server_id") is not None and kwargs.get("service_id") is not None:
		query = GitSetting.select().where(
			(GitSetting.server_id == kwargs.get("server_id")) & (GitSetting.service_id == kwargs.get("service_id")))
	else:
		query = GitSetting.select().order_by(GitSetting.id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res

def select_backups(**kwargs):
	if kwargs.get("server") is not None and kwargs.get("rserver") is not None:
		query = Backup.select().where((Backup.server == kwargs.get("server")) & (Backup.rhost == kwargs.get("rserver")))
	else:
		query = Backup.select().order_by(Backup.id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_s3_backups(**kwargs):
	if kwargs.get("server") is not None and kwargs.get("bucket") is not None:
		query = S3Backup.select().where(
			(S3Backup.server == kwargs.get("server")) &
			(S3Backup.s3_server == kwargs.get("s3_server")) &
			(S3Backup.bucket == kwargs.get("bucket"))
		)
	else:
		query = S3Backup.select().order_by(S3Backup.id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def check_exists_backup(server: str) -> bool:
	try:
		backup = Backup.get(Backup.server == server)
	except Exception:
		pass
	else:
		if backup.id is not None:
			return True
		else:
			return False


def check_exists_s3_backup(server: str) -> bool:
	try:
		backup = S3Backup.get(S3Backup.server == server)
	except Exception:
		pass
	else:
		if backup.id is not None:
			return True
		else:
			return False
