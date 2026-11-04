"""Lists UI API and compatible legacy file endpoints."""
from typing import Literal

from flask import request
from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required
from pydantic import ValidationError

from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.roxywi.class_models import GroupQuery, ListRequest
from app.modules.common.common_classes import SupportClass
from app.modules.service import haproxy_lists as lists
from app.modules.service.haproxy_list_models import ListChange, ListIdentity
from app.modules.config import add
from app.modules.roxywi.error_handler import ERROR_CODE_MAPPING, safe_error_message


def error_response(error: Exception):
    if isinstance(error, ValidationError):
        return {'status': 'failed', 'validation_error': {'body_params':
                error.errors(include_url=False, include_context=False, include_input=False)}}, 400
    if isinstance(error, lists.ListError):
        return {'status': 'failed', 'error': error.code, 'code': error.code, 'nodes': error.nodes}, error.status
    status = next((code for error_type, code in ERROR_CODE_MAPPING.items()
                   if isinstance(error, error_type)), 500)
    return {'error': f'Cannot update HAProxy list: {safe_error_message(error)}'}, status


class HaproxyListsView(MethodView):
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def get(self, service: str, server_ip: str, query: GroupQuery):
        group = SupportClass.return_group_id(query)
        try:
            if request.args.get('name'):
                identity = ListIdentity(name=request.args['name'], color=request.args.get('color'))
                return lists.detail(server_ip, group, identity)
            return lists.catalog(server_ip, group)
        except Exception as error:
            return error_response(error)

    @validate(body=ListChange)
    def put(self, service: str, server_ip: str, body: ListChange):
        # The new UI always operates in the active group; all discovered peers are checked too.
        from flask import g
        try:
            return lists.change(server_ip, int(g.user_params['group_id']), body)
        except Exception as error:
            return error_response(error)


class HaproxyListView(MethodView):
    """Retain existing API URLs while routing writes through the shared service."""
    decorators = HaproxyListsView.decorators

    @validate(query=GroupQuery)
    def get(self, service: str, list_name: str, color: Literal['white', 'black'], query: GroupQuery):
        group = SupportClass.return_group_id(query)
        try:
            identity = ListIdentity(name=list_name, color=color)
            return {'id': f'{group}-{color}-{identity.name}', 'name': identity.name,
                    'color': color, 'group_id': group, 'data': add.get_bwlist(color, group, identity.name)}
        except Exception as error:
            return error_response(error)

    @validate(body=ListRequest)
    def post(self, service: str, body: ListRequest):
        group = SupportClass.return_group_id(body)
        try:
            identity = ListIdentity(name=body.name, color=body.color)
            if body.action is None and not body.content:
                add.create_bwlist(body.server_ip, identity.name, identity.color, group)
                data = ''
            else:
                data = add.save_bwlist(identity.name, body.content or '', identity.color, group,
                                       str(body.server_ip), body.action or 'save')
            return {'status': 'Ok', 'id': f'{group}-{identity.color}-{identity.name}', 'data': data}
        except Exception as error:
            return error_response(error)

    @validate(body=ListRequest)
    def put(self, service: str, body: ListRequest):
        group = SupportClass.return_group_id(body)
        try:
            data = add.save_bwlist(body.name, body.content or '', body.color, group,
                                   str(body.server_ip), body.action or 'save')
            return {'status': 'Ok', 'data': data}
        except Exception as error:
            return error_response(error)

    @validate(body=ListRequest)
    def delete(self, service: str, body: ListRequest):
        group = SupportClass.return_group_id(body)
        try:
            add.delete_bwlist(body.name, body.color, group, str(body.server_ip))
            return '', 204
        except Exception as error:
            return error_response(error)
