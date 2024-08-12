from app.modules.db.db_model import Backup, S3Backup, GitSetting
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound


def insert_backup_job(server, rserver, rpath, backup_type, time, cred, description):
	try:
		return Backup.insert(
			server=server, rhost=rserver, rpath=rpath, type=backup_type, time=time,
			cred_id=cred, description=description
		).execute()
	except Exception as e:
		out_error(e)


def insert_s3_backup_job(**kwargs):
	try:
		return S3Backup.insert(**kwargs).execute()
	except Exception as e:
		out_error(e)


def update_backup(server, rserver, rpath, backup_type, time, cred, description, backup_id):
	backup_update = Backup.update(
		server=server, rhost=rserver, rpath=rpath, type=backup_type, time=time,
		cred_id=cred, description=description
	).where(Backup.id == backup_id)
	try:
		backup_update.execute()
	except Exception as e:
		out_error(e)


def delete_backups(backup_id: int) -> None:
	try:
		Backup.delete().where(Backup.id == backup_id).execute()
	except Exception as e:
		out_error(e)


def delete_s3_backups(backup_id: int) -> bool:
	try:
		S3Backup.delete().where(S3Backup.id == backup_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_git(server_id, service_id, repo, branch, period, cred, description) -> int:
	try:
		return GitSetting.insert(
			server_id=server_id, service_id=service_id, repo=repo, branch=branch, period=period,
			cred_id=cred, description=description
		).execute()
	except Exception as e:
		out_error(e)


def delete_git(git_id: int) -> None:
	try:
		GitSetting.delete().where(GitSetting.id == git_id).execute()
	except Exception as e:
		out_error(e)


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
		return query.execute()
	except Exception as e:
		out_error(e)


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


def get_backup(backup_id: int, model: str) -> Backup:
	models = {
		'fs': Backup,
		's3': S3Backup,
		'git': GitSetting,
	}
	model = models[model]
	try:
		return model.get(model.id == backup_id)
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
