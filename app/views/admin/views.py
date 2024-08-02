from typing import Optional

from flask.views import MethodView
from flask_pydantic import validate
from flask import render_template, jsonify, request, g
from playhouse.shortcuts import model_to_dict
from flask_jwt_extended import jwt_required

import app.modules.db.sql as sql
import app.modules.db.cred as cred_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.roxywi.group as group_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.server.ssh as ssh_mod
import app.modules.tools.smon as smon_mod
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.exception import RoxywiGroupMismatch, RoxywiResourceNotFound
from app.modules.roxywi.class_models import (
    BaseResponse, IdResponse, IdDataResponse, ServerRequest, GroupQuery, SettingsRequest
)
from app.modules.common.common_classes import SupportClass


class SettingsView(MethodView):
    methods = ['GET', 'POST']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=2), check_group()]

    @validate(query=GroupQuery)
    def get(self, section: Optional[str], query: GroupQuery):
        """
        Get Settings
        ---
        tags:
          - Settings
        summary: Get settings of the application.
        description: Returns either all settings or settings from the specified section.
        parameters:
        - name: section
          in: path
          description: The name of the settings section. Only 'main', 'smon', 'rabbitmq', 'ldap', 'monitoring', 'logs', 'haproxy', 'nginx', 'apache', 'keepalived' are allowed. If none get all settings.
          required: true
          type: string
          enum: ['main', 'smon', 'rabbitmq', 'ldap', 'monitoring', 'logs', 'haproxy', 'nginx', 'apache', 'keepalived']
        - name: group_id
          in: query
          description: This parameter is used only for the superAdmin role.
          required: false
          type: integer
        produces:
          - application/json
        responses:
          200:
            description: OK
            schema:
              type: array
              items:
                type: object
                properties:
                  desc:
                    type: string
                    description: The description of the setting.
                    example: "The path for NGINX logs"
                  group:
                    type: integer
                    description: The group number of the setting.
                    example: 1
                  param:
                    type: string
                    description: The parameter name of the setting.
                    example: "nginx_path_logs"
                  section:
                    type: string
                    description: The section name of the setting.
                    example: "nginx"
                  value:
                    type: string
                    description: The value of the setting.
                    example: "/var/log/nginx/"
        """
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot get Settings')

        settings = sql.get_setting('', group_id=group_id, section=section, all=1)

        return jsonify([model_to_dict(setting) for setting in settings])

    @validate(body=SettingsRequest, query=GroupQuery)
    def post(self, section: str, body: SettingsRequest, query: GroupQuery):
        """
        Update settings
        ---
        tags:
          - Settings
        summary: Create or update a setting.
        description: Can be used to create a new setting or update an existing one in the specified section.
        parameters:
        - name: section
          in: path
          description: The name of the settings section. Only 'main', 'smon', 'rabbitmq', 'ldap', 'monitoring', 'logs', 'haproxy', 'nginx', 'apache', 'keepalived' are allowed. If none get all settings.
          required: true
          type: string
          enum: ['main', 'smon', 'rabbitmq', 'ldap', 'monitoring', 'logs', 'haproxy', 'nginx', 'apache', 'keepalived']
        - name: group_id
          in: query
          description: The parameter is used only for the superAdmin role.
          required: false
          type: integer
        - name: body
          in: body
          description: Updated settings values.
          required: true
          schema:
            type: object
            properties:
              param:
                type: string
                description: The parameter name of the setting.
              value:
                type: string
                description: The new value for the setting.
            example:
              param: "some_param"
              value: "some_value"
        produces:
          - application/json
        responses:
          201:
            description: OK
        """
        try:
            val = body.value.replace('92', '/')
        except Exception:
            val = body.value
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot get Settings')
        try:
            sql.update_setting(body.param, val, group_id)
        except Exception as e:
            roxywi_common.handle_json_exceptions(e, 'Cannot update settings')
        roxywi_common.logging('Roxy-WI server', f'The {body.param} setting has been changed to: {val}', roxywi=1, login=1)

        if body.param == 'master_port':
            try:
                smon_mod.change_smon_port(int(val))
            except Exception as e:
                return f'{e}'
        return BaseResponse().model_dump(mode='json'), 201
