from typing import Union

from ansible.module_utils.common.text.converters import jsonify
from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required
from playhouse.shortcuts import model_to_dict

import app.modules.db.server as server_sql
import app.modules.db.portscanner as ps_sql
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.class_models import PortScannerRequest, BaseResponse
from app.modules.db.db_model import PortScannerSettings, PortScannerHistory
from app.modules.common.common_classes import SupportClass


class PortScannerView(MethodView):
    methods = ['GET', 'POST']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @staticmethod
    def get(server_id: Union[int, str]):
        """
        Port scanner operations for managing and retrieving scanner configurations.
        ---
        tags:
          - Port Scanner
        parameters:
          - in: path
            name: server_id
            type: integer
            required: true
            description: ID or IP address of the server.
        responses:
          200:
            description: A JSON object containing the port scanner settings.
            schema:
              type: object
              properties:
                enabled:
                  type: boolean
                  description: Indicates if the port scanner is enabled.
                history:
                  type: boolean
                  description: Indicates if the port scanner keeps a history.
                notify:
                  type: boolean
                  description: Indicates if notifications are enabled for the port scanner.
          404:
            description: Server not found.
          500:
            description: An error occurred while retrieving the port scanner settings.
        """
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find server')

        try:
            ps_settings = ps_sql.get_port_scanner_settings(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get Portscanner settings')

        return jsonify(model_to_dict(ps_settings, recurse=False, exclude=[PortScannerSettings.user_group_id]))


    @validate(body=PortScannerRequest)
    def post(self, server_id: Union[int, str], body: PortScannerRequest):
        """
        Updates the port scanner settings for a specific server.
        ---
        tags:
          - Port Scanner
        parameters:
          - in: path
            name: server_id
            type: integer
            required: true
            description: The ID or IP of the server
          - in: body
            name: body
            required: true
            schema:
              type: object
              properties:
                enabled:
                  type: boolean
                  description: Indicates if the port scanner is enabled
                history:
                  type: boolean
                  description: Indicates if the port scanner keeps a history
                notify:
                  type: boolean
                  description: Indicates if notifications are enabled for the port scanner
        responses:
          201:
            description: Successfully updated the port scanner settings
          default:
            description: Unexpected error
        """
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find server')

        try:
            server = server_sql.get_server_by_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find server')

        try:
            ps_sql.insert_port_scanner_settings(server_id, server.group_id, body.enabled, body.notify, body.history)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot insert Portscanner settings')

        return BaseResponse().model_dump(), 201


class PortScannerPortsView(MethodView):
    methods = ['GET']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @staticmethod
    def get(server_id: Union[int, str]):
        """
        Port scanner ports information retrieval for a specific server.
        ---
        description: Retrieves the list of open ports and their details for a specific server.
        tags:
          - Port Scanner
        parameters:
          - in: path
            name: server_id
            type: integer
            required: true
            description: ID or IP address of the server.
        responses:
          200:
            description: A JSON array containing details of open ports.
            schema:
              type: array
              items:
                type: object
                properties:
                  port:
                    type: integer
                    description: The port number.
                  status:
                    type: string
                    description: The status of the port, e.g., "opened".
                  service_name:
                    type: string
                    description: The name of the service running on the port.
                  date:
                    type: string
                    format: date-time
                    description: The date and time when the port was last checked.
          404:
            description: Server not found.
          500:
            description: An error occurred while retrieving the port scanner information.
        """
        try:
            server_ip = SupportClass(False).return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find server')

        try:
            ports = ps_sql.select_port_scanner_history(server_ip)
            ports_list = []
            for port in ports:
                ports_list.append(model_to_dict(port, exclude=[PortScannerHistory.serv]))
            return jsonify(ports_list)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get Portscanner history')
