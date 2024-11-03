from app.modules.db.db_model import LetsEncrypt, Server
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound


def get_le(le_id: int) -> LetsEncrypt:
    try:
        return LetsEncrypt.get(LetsEncrypt.id == le_id)
    except LetsEncrypt.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def get_le_with_group(le_id: int, group_id: int) -> LetsEncrypt:
    try:
        return LetsEncrypt.select().join(Server).where(
            (LetsEncrypt.id == le_id) &
            (Server.group_id == group_id)
        ).get()
    except LetsEncrypt.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def select_le_with_group(group_id: int) -> LetsEncrypt:
    try:
        return LetsEncrypt.select().join(Server).where(Server.group_id == group_id).execute()
    except Exception as e:
        out_error(e)


def insert_le(**kwargs) -> int:
    try:
        return LetsEncrypt.insert(**kwargs).execute()
    except Exception as e:
        out_error(e)


def update_le(le_id: int, **kwargs) -> int:
    try:
        return LetsEncrypt.update(**kwargs).where(LetsEncrypt.id == le_id).execute()
    except LetsEncrypt.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def delete_le(le_id: int) -> None:
    try:
        LetsEncrypt.delete().where(LetsEncrypt.id == le_id).execute()
    except Exception as e:
        out_error(e)
