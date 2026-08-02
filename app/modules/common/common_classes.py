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
            server = server_sql.get_server_by_ip(server_id)
        else:
            server = server_sql.get_server(server_id)
        roxywi_common.require_active_group_access(server.group_id)

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
                roxywi_common.require_active_group_access(body.group_id)
                return body.group_id
        else:
            return int(g.user_params['group_id'])
