from flask.views import MethodView
from flask_pydantic import validate
from flask import render_template, jsonify, request, g
from playhouse.shortcuts import model_to_dict
from flask_jwt_extended import jwt_required

from app.modules.db.db_model import Cred
import app.modules.db.cred as cred_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.roxywi.group as group_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.server.ssh as ssh_mod
import app.modules.server.server as server_mod
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.exception import RoxywiGroupMismatch, RoxywiResourceNotFound
from app.modules.roxywi.class_models import (
    BaseResponse, IdResponse, IdDataResponse, ServerRequest, GroupQuery, GroupRequest, CredRequest, CredUploadRequest
)
from app.modules.common.common_classes import SupportClass


class ServerView(MethodView):
    methods = ["GET", "POST", "PUT", "DELETE"]
    decorators = [jwt_required(), page_for_admin(level=2), check_group()]

    def __init__(self, is_api=False):
        self.is_api = is_api

    @validate(query=GroupQuery)
    def get(self, server_id: int, query: GroupQuery):
        """
        Retrieve server information based on GroupQuery
        ---
        tags:
          - 'Server'
        parameters:
          - in: 'path'
            name: 'server_id'
            description: 'ID of the Server to retrieve'
            required: true
            type: 'integer'
          - in: 'query'
            name: 'group_id'
            description: 'GroupQuery to filter servers. Only for superAdmin role'
            required: false
            type: 'integer'
        responses:
          200:
            description: Successful operation
            schema:
              type: 'object'
              properties:
                haproxy_active:
                  type: 'integer'
                haproxy_alert:
                  type: 'integer'
                apache:
                  type: 'integer'
                apache_active:
                  type: 'integer'
                apache_alert:
                  type: 'integer'
                apache_metrics:
                  type: 'integer'
                cred_id:
                  type: 'integer'
                description:
                  type: 'string'
                enabled:
                  type: 'integer'
                firewall_enable:
                  type: 'integer'
                group_id:
                  type: 'integer'
                haproxy:
                  type: 'integer'
                hostname:
                  type: 'string'
                ip:
                  type: 'string'
                keepalived:
                  type: 'integer'
                keepalived_active:
                  type: 'integer'
                keepalived_alert:
                  type: 'integer'
                master:
                  type: 'integer'
                haproxy_metrics:
                  type: 'integer'
                nginx:
                  type: 'integer'
                nginx_active:
                  type: 'integer'
                nginx_alert:
                  type: 'integer'
                nginx_metrics:
                  type: 'integer'
                port:
                  type: 'integer'
                pos:
                  type: 'integer'
                protected:
                  type: 'integer'
                server_id:
                  type: 'integer'
                type_ip:
                  type: 'integer'
          default:
            description: Unexpected error
        """
        group_id = SupportClass.return_group_id(query)
        try:
            server = server_sql.get_server_with_group(server_id, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group')
        return jsonify(model_to_dict(server))

    @validate(body=ServerRequest)
    def post(self, body: ServerRequest):
        """
        Create a new server
        ---
        tags:
          - Server
        parameters:
          - in: body
            name: body
            schema:
              id: NewServer
              required:
                - hostname
                - ip
                - enabled
                - creds_id
                - port
                - description
              properties:
                hostname:
                  type: string
                  description: The server name
                ip:
                  type: string
                  description: The server IP address
                enabled:
                  type: integer
                  description: If server is enabled or not
                creds_id:
                  type: integer
                  description: The ID of the credentials
                port:
                  type: integer
                  description: The port number
                description:
                  type: string
                  description: The server description
                group_id:
                  type: integer
                  description: The ID of the group to create the server for. Only for superAdmin role
        responses:
          201:
            description: Server creation successful
        """
        group = SupportClass.return_group_id(body)

        try:
            last_id = server_mod.create_server(
                body.hostname, str(body.ip), group, body.type_ip, body.enabled, body.master, body.cred_id, body.port, body.description,
                body.haproxy, body.nginx, body.apache, body.firewall_enable
            )
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create a server')

        roxywi_common.logging(body.ip, f'A new server {body.hostname} has been created', login=1, keep_history=1, service='server')
        try:
            server_mod.update_server_after_creating(body.hostname, str(body.ip))
        except Exception as e:
            roxywi_common.logging(body.ip, f'Cannot get system info from {body.hostname}: {e}', login=1, keep_history=1, service='server', mes_type='error')

        if self.is_api:
            return IdResponse(id=last_id).model_dump(mode='json'), 201
        else:
            try:
                user_subscription = roxywi_common.return_user_status()
            except Exception:
                user_subscription = roxywi_common.return_unsubscribed_user_status()
            lang = roxywi_common.get_user_lang_for_flask()
            kwargs = {
                'groups': group_sql.select_groups(),
                'servers': server_sql.select_servers(server=body.ip),
                'lang': lang,
                'masters': server_sql.select_servers(get_master_servers=1),
                'sshs': cred_sql.select_ssh(group=group),
                'user_subscription': user_subscription,
                'adding': 1
            }
            data = render_template('ajax/new_server.html', **kwargs)
            return IdDataResponse(data=data, id=last_id), 201

    @validate(body=ServerRequest)
    def put(self, server_id: int, body: ServerRequest):
        """
        Update a server
        ---
        tags:
          - Server
        parameters:
          - in: 'path'
            name: 'server_id'
            description: 'ID of the User to retrieve'
            required: true
            type: 'integer'
          - in: body
            name: body
            schema:
              id: UpdateServer
              required:
                - name
                - enabled
                - creds_id
                - port
                - description
              properties:
                name:
                  type: string
                  description: The server name
                enabled:
                  type: integer
                  description: If server is enabled or not
                creds_id:
                  type: integer
                  description: The ID of the credentials
                port:
                  type: integer
                  description: The port number
                description:
                  type: string
                  description: The server description
                group_id:
                  type: integer
                  description: The ID of the group to update the server for. Only for superAdmin role
        responses:
          201:
            description: Server update successful
       """
        group_id = SupportClass.return_group_id(body)

        try:
            server_sql.update_server(
                body.hostname, group_id, body.type_ip, body.enabled, body.master, server_id, body.cred_id, body.port, body.description,
                body.firewall_enable, body.protected
            )
            server_ip = server_sql.select_server_ip_by_id(server_id)
            roxywi_common.logging(server_ip, f'The server {body.hostname} has been update', roxywi=1, login=1, keep_history=1, service='server')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update server')

        return BaseResponse().model_dump(mode='json'), 201

    @staticmethod
    def delete(server_id: int):
        """
        Delete a server
        ---
        tags:
          - Server
        parameters:
          - in: 'path'
            name: 'server_id'
            description: 'ID of server to delete'
            required: true
            type: 'integer'
        responses:
          204:
            description: Server deletion successful
        """
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')
        try:
            server_mod.delete_server(server_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete server')


class ServersView(MethodView):
    methods = ["GET"]
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=2), check_group()]

    @validate(query=GroupQuery)
    def get(self, query: GroupQuery):
        """
        Retrieve servers information based on GroupQuery
        ---
        tags:
          - 'Server'
        parameters:
          - in: 'query'
            name: 'GroupQuery'
            description: 'GroupQuery to filter servers. Only for superAdmin role'
            required: false
            type: 'integer'
        responses:
          200:
            description: 'Servers Information'
            schema:
              type: 'array'
              items:
                type: 'object'
                properties:
                  haproxy_active:
                    type: 'integer'
                  haproxy_alert:
                    type: 'integer'
                  apache:
                    type: 'integer'
                  apache_active:
                    type: 'integer'
                  apache_alert:
                    type: 'integer'
                  apache_metrics:
                    type: 'integer'
                  cred_id:
                    type: 'integer'
                  description:
                    type: 'string'
                  enabled:
                    type: 'integer'
                  firewall_enable:
                    type: 'integer'
                  group_id:
                    type: 'integer'
                  haproxy:
                    type: 'integer'
                  hostname:
                    type: 'string'
                  ip:
                    type: 'string'
                  keepalived:
                    type: 'integer'
                  keepalived_active:
                    type: 'integer'
                  keepalived_alert:
                    type: 'integer'
                  master:
                    type: 'integer'
                  haproxy_metrics:
                    type: 'integer'
                  nginx:
                    type: 'integer'
                  nginx_active:
                    type: 'integer'
                  nginx_alert:
                    type: 'integer'
                  nginx_metrics:
                    type: 'integer'
                  port:
                    type: 'integer'
                  pos:
                    type: 'integer'
                  protected:
                    type: 'integer'
                  server_id:
                    type: 'integer'
                  type_ip:
                    type: 'integer'
          default:
            description: Unexpected error
        """
        group_id = SupportClass.return_group_id(query)
        try:
            servers = server_sql.select_servers_with_group(group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group')
        servers_list = [model_to_dict(server) for server in servers]
        return jsonify(servers_list)


class ServerGroupView(MethodView):
    methods = ["GET", "POST", "PUT", "DELETE"]
    decorators = [jwt_required(), get_user_params(), page_for_admin()]

    def __init__(self):
        """
        Initialize ServerGroupView instance
        """
        if request.method not in ('GET', 'DELETE'):
            self.json_data = request.get_json()
        else:
            self.json_data = None

    def get(self, group_id: int):
        """
        Retrieve group information for a specific group_id
        ---
        tags:
          - 'Group'
        parameters:
          - in: 'path'
            name: 'group_id'
            description: 'ID of the group to retrieve to get the group'
            required: true
            type: 'integer'
        responses:
          200:
            description: 'Group Information'
            schema:
              type: 'object'
              properties:
                description:
                  type: 'string'
                  description: 'Description of the server group'
                group_id:
                  type: 'integer'
                  description: 'Server group ID'
                name:
                  type: 'string'
                  description: 'Name of the server group'
          404:
            description: 'Server group not found'
        """
        try:
            groups = group_sql.select_groups(id=group_id)
            for group in groups:
                return model_to_dict(group)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group')

    @validate(body=GroupRequest)
    def post(self, body: GroupRequest):
        """
        Create a new group
        ---
        tags:
          - Group
        parameters:
          - in: body
            name: body
            schema:
              id: NewGroup
              required:
                - name
                - description
              properties:
                name:
                  type: string
                  description: The group name
                description:
                  type: string
                  description: The group description
        responses:
          201:
            description: Group creation successful
        """
        try:
            last_id = group_sql.add_group(body.name, body.description)
            roxywi_common.logging('Roxy-WI server', f'A new group {body.name} has been created', roxywi=1, login=1)
            return IdResponse(id=last_id).model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create group')

    @validate(body=GroupRequest)
    def put(self, group_id: int, body: GroupRequest):
        """
        Update a group
        ---
        tags:
          - Group
        parameters:
          - in: 'path'
            name: 'group_id'
            description: 'Group ID to change'
            required: true
            type: 'integer'
          - in: body
            name: body
            schema:
              id: UpdateGroup
              required:
                - name
                - id
              properties:
                name:
                  type: string
                  description: The group name
                description:
                  type: string
                  description: The group description
        responses:
          201:
            description: Group update successful
       """

        try:
            group_mod.update_group(group_id, body.name, body.description)
            return BaseResponse(), 201
        except Exception as e:
            roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update group')

    def delete(self, group_id: int):
        """
        Delete a group
        ---
        tags:
          - Group
        parameters:
          - in: 'path'
            name: 'group_id'
            description: 'Group ID to delete'
            required: true
            type: 'integer'
        responses:
          204:
            description: Group deletion successful
        """
        try:
            self._check_is_user_and_group(group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get user or group'), 404
        try:
            group_mod.delete_group(group_id)
            return jsonify({'status': 'Ok'}), 204
        except Exception as e:
            roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete group')

    @staticmethod
    def _check_is_user_and_group(group_id: int):
        try:
            groups = group_sql.get_group_name_by_id(group_id)
            if len(groups) == 0:
                raise RoxywiResourceNotFound
        except Exception as e:
            raise e


class ServerGroupsView(MethodView):
    methods = ["GET"]
    decorators = [jwt_required(), get_user_params(), page_for_admin()]

    def get(self):
        """
        This endpoint allows to get server groups.
        ---
        tags:
          - Group
        responses:
          200:
            description: Server groups retrieved successfully
            schema:
              type: array
              items:
                type: object
                properties:
                  description:
                    type: string
                  group_id:
                    type: integer
                  name:
                    type: string
          default:
            description: Unexpected error
        """
        groups_list = []
        groups = group_sql.select_groups()
        for group in groups:
            groups_list.append(model_to_dict(group))
        return jsonify(groups_list)


class CredView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=2), check_group()]

    def __init__(self, is_api=False):
        self.is_api = is_api

    @staticmethod
    def get(creds_id: int):
        """
        Retrieve credential information for a specific ID
        ---
        tags:
          - 'SSH credentials'
        parameters:
          - in: 'path'
            name: 'creds_id'
            description: 'ID of the credential to retrieve'
            required: true
            type: 'integer'
        responses:
          200:
            description: 'Individual Credential Information'
            schema:
              type: 'object'
              properties:
                group_id:
                  type: 'integer'
                  description: 'Group ID the credential belongs to'
                id:
                  type: 'integer'
                  description: 'Credential ID'
                key_enabled:
                  type: 'integer'
                  description: 'Key status of the credential'
                name:
                  type: 'string'
                  description: 'Name of the credential'
                username:
                  type: 'string'
                  description: 'Username associated with the credential'
          404:
            description: 'Credential not found'
        """
        group_id = int(g.user_params['group_id'])
        try:
            creds = cred_sql.get_ssh_by_id_and_group(creds_id, group_id)
            for cred in creds:
                return jsonify(model_to_dict(cred, exclude=[Cred.password, Cred.passphrase])), 200
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get credentials')

    @validate(body=CredRequest)
    def post(self, body: CredRequest):
        """
        Create a new credential entry
        ---
        tags:
          - SSH credentials
        parameters:
          - in: 'path'
            name: 'creds_id'
            description: 'ID of the credential to retrieve'
            required: true
            type: 'integer'
          - in: body
            name: body
            schema:
              id: AddCredentials
              required:
                - group_шв
                - name
                - username
                - key_enabled
                - password
              properties:
                group_id:
                  type: integer
                  description: The ID of the group to create the credential for. Only for superAdmin role
                name:
                  type: string
                  description: The credential name
                username:
                  type: string
                  description: The username
                key_enabled:
                  type: integer
                  description: If key is enabled or not
                password:
                  type: string
                  description: The password
        responses:
          201:
            description: Credential addition successful
        """
        group_id = SupportClass.return_group_id(body)
        try:
            return ssh_mod.create_ssh_cred(body.name, body.password, group_id, body.username, body.key_enabled, self.is_api)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create new cred')

    @validate(body=CredRequest)
    def put(self, creds_id: int, body: CredRequest):
        """
        Update a credential entry
        ---
        tags:
          - SSH credentials
        parameters:
          - in: 'path'
            name: 'creds_id'
            description: 'ID of the credential to retrieve'
            required: true
            type: 'integer'
          - in: body
            name: body
            schema:
              id: UpdateCredentials
              required:
                - name
                - username
                - key_enabled
                - password
              properties:
                group_id:
                  type: integer
                  description: The ID of the group to create the credential for. Only for superAdmin role
                name:
                  type: string
                  description: The credential name
                username:
                  type: string
                  description: The username
                key_enabled:
                  type: integer
                  description: If key is enabled or not
                password:
                  type: string
                  description: The password
        responses:
          201:
            description: Credential update successful
        """
        group_id = SupportClass.return_group_id(body)
        try:
            self._check_is_correct_group(creds_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, ''), 404

        try:
            ssh_mod.update_ssh_key(creds_id, body.name, body.password, body.key_enabled, body.username, group_id)
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update SSH key')

    def delete(self, creds_id: int):
        """
        Delete a credential entry
        ---
        tags:
          - SSH credentials
        parameters:
          - in: 'path'
            name: 'creds_id'
            description: 'ID of the credential to retrieve'
            required: true
            type: 'integer'
        responses:
          204:
            description: Credential deletion successful
        """
        try:
            self._check_is_correct_group(creds_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, ''), 404

        try:
            ssh_mod.delete_ssh_key(creds_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete SSH key')

    @validate(body=CredUploadRequest)
    def patch(self, creds_id: int, body: CredUploadRequest):
        """
        Upload an SSH private key
        ---
        tags:
          - SSH credentials
        parameters:
         - in: 'path'
           name: 'creds_id'
           description: 'ID of the credential to retrieve'
           required: true
           type: 'integer'
         - in: body
           name: body
           schema:
             id: UploadSSHKey
             required:
               - private_key
               - passphrase
             properties:
               private_key:
                 type: string
                 description: The private key string
               passphrase:
                 type: string
                 description: The passphrase
        responses:
          201:
            description: SSH key upload successful
        """
        try:
            self._check_is_correct_group(creds_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, ''), 404

        try:
            ssh_mod.upload_ssh_key(creds_id, body.private_key, body.passphrase)
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot upload SSH key')

    @staticmethod
    def _check_is_correct_group(creds_id: int):
        if g.user_params['role'] == 1:
            return True
        try:
            ssh = cred_sql.get_ssh(creds_id)
        except RoxywiResourceNotFound:
            raise RoxywiResourceNotFound
        if ssh.group_id != g.user_params['group_id']:
            raise RoxywiGroupMismatch


class CredsView(MethodView):
    methods = ['GET']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=2), check_group()]

    @validate(query=GroupQuery)
    def get(self, query: GroupQuery):
        """
        Retrieve credential information based on group_id
        ---
        tags:
          - 'SSH credentials'
        parameters:
          - in: 'query'
            name: 'group_id'
            description: 'GroupQuery to filter servers. Only for superAdmin role'
            required: false
            type: 'integer'
        responses:
          200:
            description: 'Credentials Information'
            schema:
              type: 'array'
              items:
                type: 'object'
                properties:
                  group_id:
                    type: 'integer'
                    description: 'Group ID the credential belongs to'
                  id:
                    type: 'integer'
                    description: 'Credential ID'
                  key_enabled:
                    type: 'integer'
                    description: 'Key status of the credential'
                  name:
                    type: 'string'
                    description: 'Name of the credential'
                  username:
                    type: 'string'
                    description: 'Username of the credential'
        """
        group_id = SupportClass.return_group_id(query)
        try:
            creds = cred_sql.select_ssh(group=group_id)
            json_data = []
            for cred in creds:
                json_data.append(model_to_dict(cred, exclude=[Cred.password, Cred.passphrase]))
            return jsonify(json_data), 200
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get credentials')


class ServerIPView(MethodView):
    class ServersView(MethodView):
        methods = ["GET"]
        decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    def get(self, server_id: int):
        """
        Retrieves IPs associated with a certain server.
        ---
        tags:
          - Server
        parameters:
          - name: server_id
            in: path
            type: string
            required: true
            description: The server's identifier, it can be either server ID or server IP.
        responses:
          200:
            description: Server IPs returned successfully.
            schema:
              type: array
              items:
                type: string
                description: An IP Address attributed to the server.
        """
        try:
            server_ip = SupportClass(False).return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        ip_lists = []
        cmd = 'sudo hostname -I | tr " " "\\n"|sed "/^$/d"'
        ips = server_mod.ssh_command(server_ip, cmd, ip="1")
        for ip in ips.split(' '):
            for i in ip.split('\r\n'):
                if i == '':
                    continue
                ip_lists.append(i)
        return jsonify(ip_lists)
