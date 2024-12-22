import ast
from typing import Union

from flask.views import MethodView
from flask_pydantic import validate
from flask import jsonify
from flask_jwt_extended import jwt_required
from playhouse.shortcuts import model_to_dict

import app.modules.db.sql as sql
import app.modules.db.le as le_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
import app.modules.service.installation as service_mod
from app.modules.db.db_model import LetsEncrypt
from app.modules.server.ssh import return_ssh_keys_path
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.class_models import LetsEncryptRequest, LetsEncryptDeleteRequest, IdResponse, GroupQuery, BaseResponse
from app.modules.common.common_classes import SupportClass


class LetsEncryptView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, le_id: int, query: GroupQuery):
        """
        Get Let's Encrypt details.
        ---
        tags:
          - Let's Encrypt
        parameters:
          - name: le_id
            in: path
            type: integer
            required: true
            description: ID of the Let's Encrypt configuration
          - name: group_id
            in: query
            type: integer
            required: false
            description: ID of the group (only for role superAdmin)
        responses:
          200:
            description: Let's Encrypt details retrieved successfully
            schema:
              type: object
              properties:
                api_key:
                  type: string
                  description: API key
                api_token:
                  type: string
                  description: API token
                description:
                  type: string
                  description: Description of the Let's Encrypt configuration
                domains:
                  type: array
                  description: List of domains associated with the Let's Encrypt configuration
                email:
                  type: string
                  description: Email associated with the Let's Encrypt account
                id:
                  type: integer
                  description: ID of the Let's Encrypt configuration
                server_id:
                  type: integer
                  description: ID of the server
                type:
                  type: string
                  description: Type of the Let's Encrypt configuration
                  enum: ['standalone', 'route53', 'cloudflare', 'digitalocean', 'linode']
        """
        group_id = SupportClass.return_group_id(query)
        try:
            le = le_sql.get_le_with_group(le_id, group_id)
            le_dict = model_to_dict(le, recurse=False)
            le_dict['domains'] = ast.literal_eval(le_dict['domains'])
            return jsonify(le_dict)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get Let\'s Encrypt')

    @validate(body=LetsEncryptRequest)
    def post(self, body: LetsEncryptRequest):
        """
        Create a Let's Encrypt configuration.
        ---
        tags:
          - Let's Encrypt
        parameters:
          - name: group_id
            in: query
            type: integer
            required: false
            description: ID of the group (only for role superAdmin)
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                api_key:
                  type: string
                  description: API key
                api_token:
                  type: string
                  description: API token
                description:
                  type: string
                  description: Description of the Let's Encrypt configuration
                domains:
                  type: array
                  description: List of domains associated with the Let's Encrypt configuration
                email:
                  type: string
                  description: Email associated with the Let's Encrypt account
                id:
                  type: integer
                  description: ID of the Let's Encrypt configuration
                server_id:
                  type: integer
                  description: ID of the server
                type:
                  type: string
                  description: Type of the Let's Encrypt configuration
                  enum: ['standalone', 'route53', 'cloudflare', 'digitalocean', 'linode']
        responses:
          201:
            description: Let's Encrypt configuration created successfully
        """
        try:
            self._create_env(body)
            last_id = le_sql.insert_le(**body.model_dump(mode='json'))
            return IdResponse(id=last_id).model_dump(), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create Let\'s Encrypt')

    @validate(body=LetsEncryptRequest, query=GroupQuery)
    def put(self, le_id: int, body: LetsEncryptRequest, query: GroupQuery):
        """
        Update a Let's Encrypt configuration.
        ---
        tags:
        - Let's Encrypt
        parameters:
          - name: le_id
            in: path
            type: integer
            required: true
            description: ID of the Let's Encrypt configuration
          - name: group_id
            in: query
            type: integer
            required: false
            description: ID of the group (only for role superAdmin)
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                api_key:
                  type: string
                  description: API key
                api_token:
                  type: string
                  description: API token
                description:
                  type: string
                  description: Description of the Let's Encrypt configuration
                domains:
                  type: array
                  description: List of domains associated with the Let's Encrypt configuration
                email:
                  type: string
                  description: Email associated with the Let's Encrypt account
                id:
                  type: integer
                  description: ID of the Let's Encrypt configuration
                server_id:
                  type: integer
                  description: ID of the server
                type:
                  type: string
                  description: Type of the Let's Encrypt configuration
                  enum: ['standalone', 'route53', 'cloudflare', 'digitalocean', 'linode']
        responses:
          201:
            description: Let's Encrypt configuration updated successfully
        """
        group_id = SupportClass.return_group_id(query)
        try:
            le = le_sql.get_le_with_group(le_id, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find Let\'s Encrypt')

        try:
            le_dict = _return_domains_list(le)
            data = LetsEncryptRequest(**le_dict)
            self._create_env(data, 'delete')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update Let\'s Encrypt on server')

        try:
            le_sql.update_le(le_id, **body.model_dump(mode='json'))
            self._create_env(body, 'install')
            return IdResponse(id=le_id).model_dump(), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update Let\'s Encrypt')

    @validate(query=GroupQuery)
    def delete(self, le_id: int, query: GroupQuery):
        """
        Delete Let's Encrypt details.
        ---
        tags:
          - Let's Encrypt
        parameters:
          - name: le_id
            in: path
            type: integer
            required: true
            description: ID of the Let's Encrypt configuration
          - name: group_id
            in: query
            type: integer
            required: false
            description: ID of the group (only for role superAdmin)
        responses:
          204:
            description: Let's Encrypt deleted successfully
        """
        group_id = SupportClass.return_group_id(query)
        try:
            le = le_sql.get_le_with_group(le_id, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find Let\'s Encrypt')

        try:
            le_dict = _return_domains_list(le)
            le_dict['emails'] = None
            data = LetsEncryptDeleteRequest(**le_dict)
            self._create_env(data, action='delete')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete Let\'s Encrypt from server')

        try:
            le_sql.delete_le(le_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete Let\'s Encrypt')

    @staticmethod
    def _create_env(data: Union[LetsEncryptRequest, LetsEncryptDeleteRequest], action: str = 'install'):
        server_ips = []
        server_ip = 'localhost'
        domains_command = ''
        servers = {}
        main_domain = data.domains[0]
        inv = {"server": {"hosts": {}}}
        masters = server_sql.is_master(server_ip)
        ssl_path = common.return_nice_path(sql.get_setting('cert_path'), is_service=0)

        if data.type == 'standalone':
            server_ip = server_sql.get_server(data.server_id).ip
            ssh_settings = return_ssh_keys_path(server_ip)
            servers[server_ip] = f"{ssh_settings['user']}@{ssh_settings['key']}"
            ansible_role = 'letsencrypt_standalone'
        else:
            master_ip = server_sql.get_server(data.server_id).ip
            ssh_settings = return_ssh_keys_path(master_ip)
            servers[master_ip] = f"{ssh_settings['user']}@{ssh_settings['key']}"
            ansible_role = 'letsencrypt'

        for domain in data.domains:
            domains_command += f' -d {domain}'

        for master in masters:
            if master[0] is not None:
                ssh_settings = return_ssh_keys_path(master[0])
                servers[master[0]] = f"{ssh_settings['user']}@{ssh_settings['key']}"

                inv['server']['hosts'][master[0]] = {
                    'token': data.api_token,
                    'secret_key': data.api_key,
                    'email': data.email,
                    'ssl_path': ssl_path,
                    'domains_command': domains_command,
                    'main_domain': main_domain,
                    'servers': servers,
                    'action': action,
                    'cert_type': data.type
                }
                server_ips.append(master[0])

        inv['server']['hosts'][server_ip] = {
            'token': data.api_token,
            'secret_key': data.api_key,
            'email': data.email,
            'ssl_path': ssl_path,
            'domains_command': domains_command,
            'main_domain': main_domain,
            'servers': servers,
            'action': action,
            'cert_type': data.type
        }

        server_ips.append(server_ip)
        if data.type != 'standalone':
            try:
                output = service_mod.run_ansible_locally(inv, ansible_role)
            except Exception as e:
                raise e
        else:
            try:
                output = service_mod.run_ansible(inv, server_ips, ansible_role)
            except Exception as e:
                raise e

        if len(output['failures']) > 0 or len(output['dark']) > 0:
            raise Exception('Cannot create certificate. Check Apache error log')


class LetsEncryptsView(MethodView):
    methods = ['GET']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, query: GroupQuery):
        """
        Get all Let's Encrypt configurations.
        ---
        tags:
          - Let's Encrypt
        parameters:
          - name: group_id
            in: query
            type: integer
            required: false
            description: ID of the group (only for role superAdmin)
        responses:
          200:
            description: List of Let's Encrypt configurations retrieved successfully
            schema:
              type: array
              items:
                type: object
                properties:
                  api_key:
                    type: string
                    description: API key
                  api_token:
                    type: string
                    description: API token
                  description:
                    type: string
                    description: Description of the Let's Encrypt configuration
                  domains:
                    type: array
                    items:
                      type: string
                    description: Domains associated with the Let's Encrypt configuration
                  email:
                    type: string
                    description: Email associated with the Let's Encrypt account
                  id:
                    type: integer
                    description: ID of the Let's Encrypt configuration
                  server_id:
                    type: integer
                    description: ID of the server
                  type:
                    type: string
                    description: Type of the Let's Encrypt configuration
        """
        group_id = SupportClass.return_group_id(query)
        le_list = []
        try:
            les = le_sql.select_le_with_group(group_id)
            for le in les:
                le_list.append(_return_domains_list(le, query.recurse))
            return jsonify(le_list)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get Let\'s Encrypts')


def _return_domains_list(le: LetsEncrypt, recurse: bool = False) -> dict:
    le_dict = model_to_dict(le, recurse=recurse)
    le_dict['domains'] = ast.literal_eval(le_dict['domains'])
    return le_dict
