from typing import Literal

from flask import jsonify
from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required

import app.modules.config.add as add_mod
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.roxywi.class_models import IdDataStrResponse, GroupQuery, ListRequest, IdStrResponse, BaseResponse
from app.modules.common.common_classes import SupportClass


class HaproxyListView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, service: str, list_name: str, color: Literal['white', 'black'], query: GroupQuery):
        """
        Get the IP address list for HAProxy.

        ---
        tags:
          - HAProxy white and black lists
        parameters:
          - in: path
            name: service
            type: 'string'
            required: true
            description: 'The service for which the list is required. Can be only `haproxy`'
          - in: path
            name: name
            type: 'string'
            required: true
            description: 'The name of the list.'
          - in: path
            name: color
            type: 'string'
            required: true
            description: 'The color of the list, can be `white` or `black`.'
          - in: query
            name: group_id
            type: 'integer'
            required: false
            description: 'The group ID, available only for the role superAdmin.'
        responses:
          200:
            description: 'Successfully retrieved the list of IP addresses.'
            schema:
              type: 'object'
              properties:
                data:
                  type: 'string'
                  description: 'The list of IP addresses.'
                  example: "192.168.1.31\\n192.168.4.1/8"
                id:
                  type: 'string'
                  description: 'The identifier of the list.'
                  example: '1-blackblacklist1.lst'
                status:
                  type: 'string'
                  description: 'The status of the request.'
                  example: "Ok"
          403:
            description: Access forbidden, superAdmin role required.
          404:
            description: List not found.
        """
        group_id = SupportClass.return_group_id(query)
        try:
            list_data = add_mod.get_bwlist(color, group_id, list_name)
            json_data = {
                'id': f'{group_id}-{color}-{list_name}.lst',
                'data': list_data,
                'name': f'{list_name}.lst',
                'color': color,
                'group_id': group_id,
            }
            return jsonify(json_data)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get list')

    @validate(body=ListRequest)
    def post(self, service: str, body: ListRequest):
        """
        Create and add content to lists

        ---
        tags:
          - HAProxy white and black lists
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum: [haproxy]
            description: The service for which the list is being submitted.
          - name: name
            in: path
            type: string
            required: true
            description: The name of the list.
          - in: body
            name: body
            description: JSON object containing details of the IP list.
            required: true
            schema:
              type: object
              required:
                - name
                - server_ip
                - content
                - color
                - action
              properties:
                name:
                  type: string
                  description: The name of the list
                  example: "whitelist1.lst"
                server_ip:
                  type: string
                  description: The IP address of the server
                  example: "127.0.0.1"
                content:
                  type: string
                  description: The content of the IP list
                  example: "92.168.1.10\\n10.0.0.1"
                color:
                  type: string
                  description: The color of the list
                  enum: [white, black]
                  example: "white"
                action:
                  type: string
                  description: The action to perform
                  example: "save"
                group_id:
                  type: integer
                  description: The group where list must be created. Only for `superAdmin` role.
        responses:
          201:
            description: Successfully created the list.
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "List successfully created."
                id:
                  type: string
                  example: "1-whitelist1.lst"
          400:
            description: Invalid input data.
          403:
            description: Access forbidden, superAdmin role required.
        """
        group_id = SupportClass.return_group_id(body)
        try:
            add_mod.create_bwlist(body.server_ip, body.name, body.color, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create list')
        if body.content == '':
            return IdStrResponse(id=f'{group_id}-{body.color}-{body.name}.lst').model_dump(mode='json')
        try:
            data = add_mod.save_bwlist(body.name, body.content, body.color, group_id, str(body.server_ip), str(body.action))
            return IdDataStrResponse(id=f'{group_id}-{body.color}-{body.name}.lst', data=data).model_dump(mode='json')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot save list')

    @validate(body=ListRequest)
    def put(self, service: str, body: ListRequest):
        """
        Update content to lists

        ---
        tags:
          - HAProxy white and black lists
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum: [haproxy]
            description: The service for which the list is being submitted.
          - name: name
            in: path
            type: string
            required: true
            description: The name of the list.
          - in: body
            name: body
            description: JSON object containing details of the IP list.
            required: true
            schema:
              type: object
              required:
                - name
                - server_ip
                - content
                - color
                - action
              properties:
                name:
                  type: string
                  description: The name of the list
                  example: "whitelist1.lst"
                server_ip:
                  type: string
                  description: The IP address of the server
                  example: "127.0.0.1"
                content:
                  type: string
                  description: The content of the IP list
                  example: "92.168.1.10\\n10.0.0.1"
                color:
                  type: string
                  description: The color of the list
                  enum: [white, black]
                  example: "white"
                action:
                  type: string
                  description: The action to perform
                  example: "save"
                group_id:
                  type: integer
                  description: The group where list must be created. Only for `superAdmin` role.
        responses:
          201:
            description: Successfully created the list.
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "List successfully created."
                id:
                  type: string
                  example: "1-whitelist1.lst"
          400:
            description: Invalid input data.
          403:
            description: Access forbidden, superAdmin role required.
        """
        group_id = SupportClass.return_group_id(body)
        try:
            add_mod.save_bwlist(body.name, body.content, body.color, group_id, body.server_ip, str(body.action))
            return BaseResponse().model_dump(mode='json')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot save list')

    @validate(body=ListRequest)
    def delete(self, service: str, body: ListRequest):
        """
        Delete HAProxy white and black list.

        ---
        tags:
          - HAProxy white and black lists
        parameters:
          - in: path
            name: service
            type: 'string'
            required: true
            description: 'The service for which the list is required. Can be only `haproxy`'
          - in: body
            name: body
            description: JSON object containing details of the IP list.
            required: true
            schema:
              type: object
              required:
                - name
                - color
              properties:
                name:
                  type: string
                  description: The name of the list
                  example: "whitelist1.lst"
                color:
                  type: string
                  description: The color of the list
                  enum: [white, black]
                  example: "white"
                group_id:
                  type: integer
                  description: The group where list must be created. Only for `superAdmin` role.
        responses:
          204:
            description: 'Successfully delete list.'
          403:
            description: Access forbidden, superAdmin role required.
          404:
            description: List not found.
        """
        group_id = SupportClass.return_group_id(body)
        try:
            add_mod.delete_bwlist(body.name, body.color, group_id, str(body.server_ip))
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete list')
