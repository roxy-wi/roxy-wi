from app.modules.db.db_model import UDPBalancer
from app.modules.db.common import out_error


def select_listeners(group_id: int) -> UDPBalancer:
    try:
        return UDPBalancer.select().where(UDPBalancer.group_id == group_id).execute()
    except Exception as e:
        out_error(e)


def insert_listener(**kwargs) -> int:
    try:
        return UDPBalancer.insert(**kwargs).execute()
    except Exception as e:
        out_error(e)


def update_listener(listener_id: int, **kwargs) -> int:
    try:
        return UDPBalancer.update(**kwargs).where(UDPBalancer.id == listener_id).execute()
    except Exception as e:
        out_error(e)


def get_listener(listener_id: int) -> UDPBalancer:
    try:
        return UDPBalancer.get(UDPBalancer.id == listener_id)
    except Exception as e:
        out_error(e)


def delete_listener(listener_id: int) -> None:
    try:
        UDPBalancer.delete().where(UDPBalancer.id == listener_id).execute()
    except Exception as e:
        out_error(e)
