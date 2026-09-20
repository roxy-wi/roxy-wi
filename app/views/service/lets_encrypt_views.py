from flask import jsonify
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask_pydantic import validate

from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, Server
from app.modules.roxywi import common
from app.modules.roxywi.class_models import LetsEncryptRequest, LetsEncryptActionRequest, GroupQuery
from app.modules.common.common_classes import SupportClass
from app.modules.service.le import le_store
from app.modules.service.common import is_protected


def accepted(le_id, task_id):
    return {'id': le_id, 'status': 'accepted', 'tasks_ids': [task_id]}, 202


def identity(query):
    return SupportClass.return_group_id(query), common.get_jwt_token_claims().get('user_id')


def protect(server_id, group_id):
    for server in le_store.targets_for(server_id, group_id):
        is_protected(server.ip, 'update certificates on')


class LetsEncryptView(MethodView):
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, le_id: int, query: GroupQuery):
        """Return certificate configuration and lifecycle state without DNS secrets.
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
                  description: Always null; DNS credentials are never returned
                api_token:
                  type: string
                  description: Always null; use has_api_token to check configuration
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
        try:
            return jsonify(le_store.public_config(le_store.get_owned(le_id, identity(query)[0]), query.recurse))
        except Exception as error:
            return common.handler_exceptions_for_json_data(error, "Cannot get Let's Encrypt")

    @validate(body=LetsEncryptRequest, query=GroupQuery)
    def post(self, body: LetsEncryptRequest, query: GroupQuery):
        """Queue certificate issuance and deployment.
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
          202:
            description: Let's Encrypt configuration accepted for asynchronous processing
        """
        try:
            group_id, user_id = identity(query)
            protect(body.server_id, group_id)
            le_id, task_id = le_store.create(body.model_dump(mode='json'), group_id, user_id)
            return accepted(le_id, task_id)
        except Exception as error:
            return common.handler_exceptions_for_json_data(error, "Cannot create Let's Encrypt")

    @validate(body=LetsEncryptRequest, query=GroupQuery)
    def put(self, le_id: int, body: LetsEncryptRequest, query: GroupQuery):
        """Apply a replacement only after successful certificate deployment.
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
          202:
            description: Let's Encrypt configuration update accepted for asynchronous processing
        """
        try:
            group_id, user_id = identity(query)
            row = le_store.get_owned(le_id, group_id)
            protect(row.server_id_id, group_id)
            protect(body.server_id, group_id)
            return accepted(le_id, le_store.update(le_id, body.model_dump(mode='json'), group_id, user_id))
        except Exception as error:
            return common.handler_exceptions_for_json_data(error, "Cannot update Let's Encrypt")

    @validate(query=GroupQuery)
    def delete(self, le_id: int, query: GroupQuery):
        """Stop renewal and remove managed ACME state; keep deployed PEMs in use.
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
          202:
            description: Let's Encrypt deletion accepted for asynchronous processing
        """
        try:
            group_id, user_id = identity(query)
            row = le_store.get_owned(le_id, group_id)
            protect(row.server_id_id, group_id)
            return accepted(le_id, le_store.action(le_id, 'delete', group_id, user_id))
        except Exception as error:
            return common.handler_exceptions_for_json_data(error, "Cannot delete Let's Encrypt")

    @validate(body=LetsEncryptActionRequest, query=GroupQuery)
    def patch(self, le_id: int, body: LetsEncryptActionRequest, query: GroupQuery):
        """Queue a renewal check, staging test, or retry of the last failed operation.
        ---
        tags:
          - Let's Encrypt
        parameters:
          - name: le_id
            in: path
            type: integer
            required: true
          - name: body
            in: body
            required: true
            schema:
              type: object
              required: [action]
              properties:
                action:
                  type: string
                  enum: [renew, test, retry]
        responses:
          202:
            description: Operation accepted; response includes tasks_ids
          409:
            description: Another operation is active or legacy migration is required
        """
        try:
            group_id, user_id = identity(query)
            row = le_store.get_owned(le_id, group_id)
            protect(row.server_id_id, group_id)
            return accepted(le_id, le_store.action(le_id, body.action, group_id, user_id))
        except Exception as error:
            return common.handler_exceptions_for_json_data(error, "Cannot run Let's Encrypt operation")


class LetsEncryptsView(MethodView):
    decorators = [jwt_required(), get_user_params(), page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, query: GroupQuery):
        """List certificate configurations and lifecycle states without DNS credentials.
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
                    description: Always null; DNS credentials are never returned
                  api_token:
                    type: string
                    description: Always null; use has_api_token to check configuration
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
        try:
            group_id = identity(query)[0]
            rows = (LetsEncrypt.select().join(Server).switch(LetsEncrypt)
                    .join(LetsEncryptState, on=(LetsEncryptState.le_id == LetsEncrypt.id))
                    .where((Server.group_id == str(group_id)) & (LetsEncryptState.status != 'deleted')))
            return jsonify([le_store.public_config(row, query.recurse) for row in rows])
        except Exception as error:
            return common.handler_exceptions_for_json_data(error, "Cannot get Let's Encrypt certificates")
