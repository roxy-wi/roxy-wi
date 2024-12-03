from typing import Union

from flask import g

import app.modules.db.server as server_sql
import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi.class_models import ServerRequest, GroupQuery, CredRequest, ChannelRequest, ListRequest
from app.middleware import get_user_params


class SupportClass:
    def __init__(self, is_id=True):
        self.is_id = is_id

    @get_user_params()
    def return_server_ip_or_id(self, server_id: Union[int, str]) -> Union[int, str]:
        if isinstance(server_id, str):
            try:
                server = server_sql.get_server_by_ip(server_id)
            except Exception as e:
                raise e
        else:
            try:
                server = server_sql.get_server(server_id)
            except Exception as e:
                raise e
        try:
            roxywi_common.is_user_has_access_to_group(g.user_params['user_id'], server.group_id)
        except Exception as e:
            roxywi_common.handler_exceptions_for_json_data(e, '')

        if self.is_id:
            return server.server_id
        else:
            return server.ip

    @staticmethod
    @get_user_params()
    def return_group_id(body: Union[ServerRequest, CredRequest, GroupQuery, ChannelRequest, ListRequest]):
        if body.group_id:
            if g.user_params['role'] == 1:
                return body.group_id
            else:
                try:
                    roxywi_common.is_user_has_access_to_group(g.user_params['user_id'], body.group_id)
                    return body.group_id
                except Exception:
                    return int(g.user_params['group_id'])
        else:
            return int(g.user_params['group_id'])
