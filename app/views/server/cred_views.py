import base64

from flask.views import MethodView
from flask_pydantic import validate
from flask import jsonify, g
from flask_jwt_extended import jwt_required

import app.modules.db.cred as cred_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.server.ssh as ssh_mod
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.exception import RoxywiGroupMismatch, RoxywiResourceNotFound
from app.modules.roxywi.class_models import BaseResponse, GroupQuery, CredRequest, CredUploadRequest
from app.modules.common.common_classes import SupportClass

class CredView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=2), check_group()]

    def __init__(self, is_api=False):
        self.is_api = is_api

    @staticmethod
    @validate(query=GroupQuery)
    def get(cred_id: int, query: GroupQuery):
        """
        Retrieve credential information for a specific ID
        ---
        tags:
          - 'SSH credentials'
        parameters:
          - in: 'path'
            name: 'cred_id'
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
                password:
                  type: 'string'
                  description: 'Password associated with the credential'
                passphrase:
                  type: 'string'
                  description: 'Password for the SSH private key'
                private_key:
                  type: 'string'
                  description: 'SSH private key in base64 encoded format'
          404:
            description: 'Credential not found'
        """
        group_id = SupportClass.return_group_id(query)
        try:
            creds = ssh_mod.get_creds(group_id=group_id, cred_id=cred_id)
            return jsonify(creds), 200
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
                 description: The private key string or base64 encoded string
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
            body.private_key = base64.b64decode(body.private_key).decode("ascii")
        except Exception:
            pass
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
                  password:
                    type: 'string'
                    description: 'Password associated with the credential'
                  passphrase:
                    type: 'string'
                    description: 'Password for the SSH private key'
                  private_key:
                    type: 'string'
                    description: 'SSH private key in base64 encoded format'
        """
        group_id = SupportClass.return_group_id(query)
        try:
            creds = ssh_mod.get_creds(group_id=group_id)
            return jsonify(creds), 200
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get credentials')
