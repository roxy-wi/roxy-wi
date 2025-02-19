from app.modules.db.db_model import UDPBalancer
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiGroupNotFound


def select_all_listeners() -> UDPBalancer:
    try:
        return UDPBalancer.select().execute()
    except UDPBalancer.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def select_listeners(group_id: int) -> UDPBalancer:
    try:
        return UDPBalancer.select().where(UDPBalancer.group_id == group_id).execute()
    except UDPBalancer.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def insert_listener(**kwargs) -> int:
    try:
        return UDPBalancer.insert(**kwargs).execute()
    except UDPBalancer.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        if e.args[0] == 1215 or str(e) == 'FOREIGN KEY constraint failed':
            raise RoxywiGroupNotFound
        out_error(e)


def update_listener(listener_id: int, **kwargs) -> int:
    try:
        return UDPBalancer.update(**kwargs).where(UDPBalancer.id == listener_id).execute()
    except UDPBalancer.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def get_listener(listener_id: int) -> UDPBalancer:
    try:
        return UDPBalancer.get(UDPBalancer.id == listener_id)
    except UDPBalancer.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)


def delete_listener(listener_id: int) -> None:
    try:
        UDPBalancer.delete().where(UDPBalancer.id == listener_id).execute()
    except UDPBalancer.DoesNotExist:
        raise RoxywiResourceNotFound
    except Exception as e:
        out_error(e)
