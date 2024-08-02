from typing import Literal
from typing import Union

from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required
from flask import jsonify, g
from playhouse.shortcuts import model_to_dict

import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.checker as checker_sql
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.roxywi.class_models import Checker
from app.modules.db.db_model import CheckerSetting


class CheckerView(MethodView):
    methods = ["GET", "POST"]
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def get(self, service: Literal['haproxy', 'nginx', 'apache', 'keepalived'], server_id: Union[int, str]):
        """
        Retrieves the status of specific checker services.
        ---
        tags:
          - Service Tools
        parameters:
          - in: path
            name: service
            type: 'integer'
            required: true
            description: The type of service (haproxy, nginx, apache, keepalived)
          - in: path
            name: server_id
            type: 'integer'
            required: true
            description: The ID or IP of the server
        responses:
          200:
            description: Successful operation
            schema:
              type: 'object'
              properties:
                server_id:
                    type: 'integer'
                    description: 'Server identifier'
                backend_alert:
                    type: 'integer'
                    description: 'Alert status for backends. Only for HAProxy and Keepalived services'
                maxconn_alert:
                    type: 'integer'
                    description: 'Alert status for max connections. Only for HAProxy service'
                email:
                    type: 'integer'
                    description: 'Status flag for email notifications'
                mm_id:
                    type: 'integer'
                    description: 'Identifier for Mattermost notifications'
                pd_id:
                    type: 'integer'
                    description: 'Identifier for PagerDuty notifications'
                service_alert:
                    type: 'integer'
                    description: 'Alert status for services'
                slack_id:
                    type: 'integer'
                    description: 'Identifier for Slack notifications'
                telegram_id:
                    type: 'integer'
                    description: 'Identifier for Telegram notifications'
                checker:
                    type: 'integer'
                    description: 'Is Checker tools enabled for this service'
                metrics:
                    type: 'integer'
                    description: 'Is Metrics tools enabled for this service'
                auto_start:
                    type: 'integer'
                    description: 'Is Auto start tools enabled for this service'
          default:
            description: Unexpected error
        """
        service_id = service_sql.select_service_id_by_slug(service)

        try:
            server = server_sql.get_server_by_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find server')

        try:
            roxywi_common.is_user_has_access_to_group(g.user_params['user_id'], server.group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            checker_settings = checker_sql.select_checker_settings_for_server(service_id, server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get settings')
        checker_setting = [model_to_dict(checker, recurse=False, exclude=[CheckerSetting.service_id, CheckerSetting.id]) for checker in checker_settings]
        server = model_to_dict(server)
        checker_setting[0]['checker'] = server[f'{service}_alert']
        checker_setting[0]['metrics'] = server[f'{service}_metrics']
        checker_setting[0]['auto_start'] = server[f'{service}_active']
        return jsonify(checker_setting)

    @validate(body=Checker)
    def post(self, service: Literal['haproxy', 'nginx', 'apache', 'keepalived'], server_id: Union[int, str], body: Checker):
        ...