import os
from typing import Union, Literal

from flask.views import MethodView
from flask_pydantic import validate
from flask import jsonify, g
from flask_jwt_extended import jwt_required
from playhouse.shortcuts import model_to_dict

import app.modules.db.add as add_sql
import app.modules.db.server as server_sql
import app.modules.config.config as config_mod
import app.modules.config.common as config_common
import app.modules.service.installation as service_mod
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.db.db_model import Server
from app.modules.roxywi.class_models import BaseResponse, DataStrResponse, HaproxyConfigRequest, GenerateConfigRequest, \
    HaproxyUserListRequest, HaproxyPeersRequest, HaproxyGlobalRequest, HaproxyDefaultsRequest, IdDataStrResponse
from app.modules.common.common_classes import SupportClass


class HaproxySectionView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def get(self, service: Literal['haproxy'], section_type: str, section_name: str, server_id: Union[int, str]):
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            _ = server_sql.get_server_with_group(server_id, g.user_params['group_id'])
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find a server')

        try:
            section = add_sql.get_section(server_id, section_type, section_name)
            output = {'server_id': section.server_id.server_id, **model_to_dict(section, recurse=False)}
            output['id'] = f'{server_id}-{section_name}'
            output.update(section.config)
            return jsonify(output)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get HAProxy section')

    def post(self,
             service: Literal['haproxy'],
             section_type: str,
             server_id: Union[int, str],
             body: Union[HaproxyConfigRequest, HaproxyUserListRequest, HaproxyPeersRequest],
             query: GenerateConfigRequest
             ):
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            server = server_sql.get_server_with_group(server_id, g.user_params['group_id'])
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find a server')
        if query.generate:
            cfg = '/tmp/haproxy-generated-config.cfg'
            os.system(f'touch {cfg}')
            inv = service_mod.generate_haproxy_section_inv(body.model_dump(mode='json'), cfg)

            try:
                output = service_mod.run_ansible_locally(inv, 'haproxy_section')
                if len(output['failures']) > 0 or len(output['dark']) > 0:
                    raise Exception('Cannot create HAProxy section. Check Apache error log')
            except Exception as e:
                return roxywi_common.handler_exceptions_for_json_data(e, f'Cannot create HAProxy section: {e}')
            try:
                with open(cfg, 'r') as file:
                    conf = file.read()
            except Exception as e:
                raise Exception(f'error: Cannot read config file: {e}')
            os.remove(cfg)
            return DataStrResponse(data=conf).model_dump(mode='json'), 200

        try:
            output = self._edit_config(service, server, body, 'create')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create HAProxy section')

        try:
            add_sql.insert_new_section(server_id, section_type, body.name, body)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot add HAProxy section')

        res = IdDataStrResponse(data=output, id=f'{server_id}-{body.name}').model_dump(mode='json')
        print(res)
        return res, 201

    def put(self,
            service: Literal['haproxy'],
            section_type: str,
            section_name: str,
            server_id: Union[int, str],
            body: Union[HaproxyConfigRequest, HaproxyUserListRequest, HaproxyPeersRequest, HaproxyGlobalRequest, HaproxyDefaultsRequest]
            ):
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            server = server_sql.get_server_with_group(server_id, g.user_params['group_id'])
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find a server')

        try:
            output = self._edit_config(service, server, body, 'create')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create HAProxy section')

        if 'Fatal' in output or 'error' in output:
            return DataStrResponse(data=output).model_dump(mode='json'), 201
        else:
            try:
                if section_name in ('global', 'defaults'):
                    add_sql.insert_or_update_new_section(server_id, section_name, section_name, body)
                else:
                    add_sql.update_section(server_id, section_type, section_name, body)
            except Exception as e:
                return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update HAProxy section')

        return DataStrResponse(data=output).model_dump(mode='json'), 201

    def delete(self, service: Literal['haproxy'], section_type: str, section_name: str, server_id: Union[int, str]):
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            server = server_sql.get_server_with_group(server_id, g.user_params['group_id'])
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find a server')

        try:
            self._edit_config(service, server, '', 'delete', section_type=section_type, section_name=section_name)
            add_sql.delete_section(server_id, section_type, section_name)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete HAProxy section')

        return BaseResponse().model_dump(mode='json'), 204

    @staticmethod
    def _edit_config(service, server: Server, body: HaproxyConfigRequest, action: Literal['create', 'delete'], **kwargs) -> str:
        cfg = config_common.generate_config_path(service, server.ip)
        if action == 'create':
            inv = service_mod.generate_haproxy_section_inv(body.model_dump(mode='json'), cfg)
        else:
            inv = service_mod.generate_haproxy_section_inv_for_del(cfg, kwargs.get('section_type'), kwargs.get('section_name'))

        try:
            config_mod.get_config(server.ip, cfg, service=service)
        except Exception as e:
            raise e

        try:
            output = service_mod.run_ansible_locally(inv, 'haproxy_section')
        except Exception as e:
            raise e

        if len(output['failures']) > 0 or len(output['dark']) > 0:
            raise Exception('Cannot create HAProxy section. Check Apache error log')

        output = config_mod.master_slave_upload_and_restart(server.ip, cfg, str(body.action), 'haproxy')

        return output


class ListenSectionView(HaproxySectionView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate()
    def get(self, service: Literal['haproxy'], section_type: Literal['listen', 'frontend', 'backend'], section_name: str, server_id: Union[int, str]):
        """
        HaproxySectionView API

        This is the HaproxySectionView API where you can get configurations of HAProxy sections.

        ---
        tags:
          - HAProxy section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_type
            in: path
            type: string
            required: true
            enum:
              - listen
              - frontend
              - backend
            description: The type of section to fetch.
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of the section to fetch.
        responses:
          200:
            description: Haproxy section configuration.
            schema:
              type: object
              properties:
                config:
                  type: object
                  properties:
                    acls:
                      type: array
                      items:
                        type: object
                    antibot:
                      type: integer
                    backend_servers:
                      type: array
                      items:
                        type: object
                        properties:
                          backup:
                            type: boolean
                          maxconn:
                            type: integer
                          port:
                            type: integer
                          port_check:
                            type: integer
                          send_proxy:
                            type: boolean
                          server:
                            type: string
                    balance:
                      type: string
                    binds:
                      type: array
                      items:
                        type: object
                        properties:
                          ip:
                            type: string
                          port:
                            type: integer
                    blacklist:
                      type: string
                    cache:
                      type: integer
                    compression:
                      type: integer
                    cookie:
                      type: object
                    ddos:
                      type: integer
                    forward_for:
                      type: integer
                    headers:
                      type: array
                      items:
                        type: object
                    health_check:
                      type: object
                    maxconn:
                      type: integer
                    mode:
                      type: string
                    name:
                      type: string
                    option:
                      type: string
                    redispatch:
                      type: integer
                    server:
                      type: integer
                    servers_check:
                      type: object
                    slow_attack:
                      type: integer
                    ssl_offloading:
                      type: integer
                    type:
                      type: string
                    waf:
                      type: integer
                    whitelist:
                      type: string
                id:
                  type: integer
                name:
                  type: string
                server_id:
                  type: integer
                type:
                  type: string
          400:
            description: Invalid parameters.
          404:
            description: Section not found.
          500:
            description: Internal server error.
        """
        return super().get(service, section_type, section_name, server_id)

    @validate(body=HaproxyConfigRequest, query=GenerateConfigRequest)
    def post(self,
             service: Literal['haproxy'],
             section_type: Literal['listen', 'frontend', 'backend'],
             server_id: Union[int, str],
             body: HaproxyConfigRequest,
             query: GenerateConfigRequest
             ):
        """
        HaproxySectionView API

        This is the HaproxySectionView API where you can create HAProxy sections.

        ---
        tags:
          - HAProxy section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_type
            in: path
            type: string
            required: true
            enum:
              - listen
              - frontend
              - backend
            description: The type of section to create.
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                acls:
                  type: array
                  items:
                    type: object
                    properties:
                      acl_if:
                        type: string
                      acl_value:
                        type: string
                      acl_then:
                        type: string
                      acl_then_value:
                        type: string
                binds:
                  type: array
                  items:
                    type: object
                    properties:
                      ip:
                        type: string
                      port:
                        type: string
                headers:
                  type: array
                  items:
                    type: object
                    properties:
                      path:
                        type: string
                      method:
                        type: string
                      name:
                        type: string
                      value:
                        type: string
                backend_servers:
                  type: array
                  items:
                    type: object
                    properties:
                      server:
                        type: string
                      port:
                        type: string
                      port_check:
                        type: string
                      maxconn:
                        type: string
                      send_proxy:
                        type: integer
                      backup:
                        type: integer
                type:
                  type: string
                server:
                  type: string
                name:
                  type: string
                mode:
                  type: string
                ssl:
                  type: object
                  properties:
                    cert:
                      type: string
                    ssl_check:
                      type: integer
                    ssl_check_backend:
                      type: integer
                maxconn:
                  type: string
                balance:
                  type: string
                health_check:
                  type: object
                  properties:
                    check:
                      type: string
                    path:
                      type: string
                    domain:
                      type: string
                compression:
                  type: string
                cache:
                  type: string
                ssl_offloading:
                  type: integer
                slow_attack:
                  type: integer
                whitelist:
                  type: string
                blacklist:
                  type: string
                forward_for:
                  type: integer
                force_close:
                  type: string
                cookie:
                  type: object
                  properties:
                    name:
                      type: string
                    domain:
                      type: string
                    dynamic:
                      type: string
                    dynamicKey:
                      type: string
                    nocache:
                      type: string
                    postonly:
                      type: string
                    prefix:
                      type: string
                option:
                  type: string
                servers_check:
                  type: object
                  properties:
                    inter:
                      type: string
                    rise:
                      type: string
                    fall:
                      type: string
                inter:
                  type: string
                circuit_breaking:
                  type: object
                  properties:
                    observe:
                      type: string
                    error_limit:
                      type: integer
                    on_error:
                      type: string
        responses:
          200:
            description: Haproxy section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().post(service, section_type, server_id, body, query)

    @validate(body=HaproxyConfigRequest)
    def put(self, service: Literal['haproxy'], section_type: Literal['listen', 'frontend', 'backend'],
            section_name: str, server_id: Union[int, str], body: HaproxyConfigRequest):
        """
        This is the HaproxySectionView API where you can update the HAProxy sections.

        ---
        tags:
          - HAProxy section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_type
            in: path
            type: string
            required: true
            enum:
              - listen
              - frontend
              - backend
            description: The type of section to update.
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of section to update.
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                acls:
                  type: array
                  items:
                    type: object
                    properties:
                      acl_if:
                        type: string
                      acl_value:
                        type: string
                      acl_then:
                        type: string
                      acl_then_value:
                        type: string
                binds:
                  type: array
                  items:
                    type: object
                    properties:
                      ip:
                        type: string
                      port:
                        type: string
                headers:
                  type: array
                  items:
                    type: object
                    properties:
                      path:
                        type: string
                      method:
                        type: string
                      name:
                        type: string
                      value:
                        type: string
                backend_servers:
                  type: array
                  items:
                    type: object
                    properties:
                      server:
                        type: string
                      port:
                        type: string
                      port_check:
                        type: string
                      maxconn:
                        type: string
                      send_proxy:
                        type: integer
                      backup:
                        type: integer
                type:
                  type: string
                server:
                  type: string
                name:
                  type: string
                mode:
                  type: string
                ssl:
                  type: object
                  properties:
                    cert:
                      type: string
                    ssl_check:
                      type: integer
                    ssl_check_backend:
                      type: integer
                maxconn:
                  type: string
                balance:
                  type: string
                health_check:
                  type: object
                  properties:
                    check:
                      type: string
                    path:
                      type: string
                    domain:
                      type: string
                compression:
                  type: string
                cache:
                  type: string
                ssl_offloading:
                  type: integer
                slow_attack:
                  type: integer
                whitelist:
                  type: string
                blacklist:
                  type: string
                forward_for:
                  type: integer
                force_close:
                  type: string
                cookie:
                  type: object
                  properties:
                    name:
                      type: string
                    domain:
                      type: string
                    dynamic:
                      type: string
                    dynamicKey:
                      type: string
                    nocache:
                      type: string
                    postonly:
                      type: string
                    prefix:
                      type: string
                option:
                  type: string
                servers_check:
                  type: object
                  properties:
                    inter:
                      type: string
                    rise:
                      type: string
                    fall:
                      type: string
                inter:
                  type: string
                circuit_breaking:
                  type: object
                  properties:
                    observe:
                      type: string
                    error_limit:
                      type: integer
                    on_error:
                      type: string
                userlist_users:
                  type: object
                  properties:
                    user:
                      type: string
                    password:
                      type: string
                    group:
                      type: string
                userlist_groups:
                  type: array
        responses:
          200:
            description: Haproxy section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().put(service, section_type, section_name, server_id, body)

    @validate()
    def delete(self, service: Literal['haproxy'], section_type: str, section_name: str, server_id: Union[int, str]):
        """
        HaproxySectionView sections API

        This is the HaproxySectionView API where you can delete configurations of HAProxy sections.

        ---
        tags:
          - HAProxy section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_type
            in: path
            type: string
            required: true
            enum:
              - listen
              - frontend
              - backend
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of the section to fetch.
        responses:
          204:
            description: Haproxy section configuration.
        """
        return super().delete(service, section_type, section_name, server_id)


class UserListSectionView(HaproxySectionView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate()
    def get(self, service: Literal['haproxy'], section_name: str, server_id: Union[int, str]):
        """
        HaproxySectionView userlist API

        This is the HaproxySectionView API where you can get configurations of HAProxy userlist sections.

        ---
        tags:
          - HAProxy userlist section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of the section to fetch.
        responses:
          200:
            description: Haproxy section configuration.
            schema:
              type: object
              properties:
                config:
                  type: object
                  properties:
                    name:
                      type: string
                id:
                  type: integer
                name:
                  type: string
                server_id:
                  type: integer
                type:
                  type: string
          400:
            description: Invalid parameters.
          404:
            description: Section not found.
          500:
            description: Internal server error.
        """
        return super().get(service, 'userlist', section_name, server_id)

    @validate(body=HaproxyUserListRequest, query=GenerateConfigRequest)
    def post(self,
             service: Literal['haproxy'],
             server_id: Union[int, str],
             body: HaproxyUserListRequest,
             query: GenerateConfigRequest
             ):
        """
        HaproxySectionView userlist API

        This is the HaproxySectionView API where you can create HAProxy userlist sections.

        ---
        tags:
          - HAProxy userlist section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                type:
                  type: string
                  example: "userlist"
                userlist_users:
                  type: array
                  items:
                    type: object
                    properties:
                      user:
                        type: string
                        example: "admin"
                      password:
                        type: string
                        example: "secretpassword"
                      group:
                        type: string
                        example: ""
                userlist_groups:
                  type: array
                  items:
                    type: string
                    example: "ops"
                name:
                  type: string
                  example: "ops_users"
        responses:
          200:
            description: Haproxy section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().post(service, 'userlist', server_id, body, query)

    @validate(body=HaproxyUserListRequest)
    def put(self, service: Literal['haproxy'], section_name: str, server_id: Union[int, str], body: HaproxyUserListRequest):
        """
        This is the HaproxySectionView API where you can update the HAProxy user list section.

        ---
        tags:
          - HAProxy userlist section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of section to update.
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                type:
                  type: string
                  example: "userlist"
                userlist_users:
                  type: array
                  items:
                    type: object
                    properties:
                      user:
                        type: string
                        example: "admin"
                      password:
                        type: string
                        example: "secretpassword"
                      group:
                        type: string
                        example: ""
                userlist_groups:
                  type: array
                  items:
                    type: string
                    example: "ops"
                name:
                  type: string
                  example: "ops_users"
        responses:
          200:
            description: Haproxy section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().put(service, 'userlist', section_name, server_id, body)

    @validate()
    def delete(self, service: Literal['haproxy'], section_name: str, server_id: Union[int, str]):
        """
        HaproxySectionView userlist API

        This is the HaproxySectionView API where you can delete configurations of HAProxy userlist sections.

        ---
        tags:
          - HAProxy userlist section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of the section to fetch.
        responses:
          204:
            description: Haproxy section configuration.
        """
        return super().delete(service, 'userlist', section_name, server_id)


class PeersSectionView(HaproxySectionView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate()
    def get(self, service: Literal['haproxy'], section_name: str, server_id: Union[int, str]):
        """
        HaproxySectionView peers API

        This is the HaproxySectionView API where you can get configurations of HAProxy userlist sections.

        ---
        tags:
          - HAProxy peers section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of the section to fetch.
        responses:
          200:
            description: Haproxy section configuration.
            schema:
              type: object
              properties:
                config:
                  type: object
                  properties:
                    name:
                      type: string
                id:
                  type: integer
                name:
                  type: string
                server_id:
                  type: integer
                type:
                  type: string
          400:
            description: Invalid parameters.
          404:
            description: Section not found.
          500:
            description: Internal server error.
        """
        return super().get(service, 'peers', section_name, server_id)

    @validate(body=HaproxyPeersRequest, query=GenerateConfigRequest)
    def post(self,
             service: Literal['haproxy'],
             server_id: Union[int, str],
             body: HaproxyPeersRequest,
             query: GenerateConfigRequest
             ):
        """
        HaproxySectionView peers API

        This is the HaproxySectionView API where you can create HAProxy userlist sections.

        ---
        tags:
          - HAProxy peers section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                type:
                  type: string
                  description: The type of the section.
                peers:
                  type: array
                  items:
                    type: object
                    properties:
                      name:
                        type: string
                        description: The name of the peer.
                      ip:
                        type: string
                        description: The IP address of the peer.
                      port:
                        type: string
                        description: The port of the peer.
                name:
                  type: string
                  description: The name of the section.
        responses:
          200:
            description: Haproxy section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().post(service, 'peers', server_id, body, query)

    @validate(body=HaproxyPeersRequest)
    def put(self, service: Literal['haproxy'], section_name: str, server_id: Union[int, str], body: HaproxyPeersRequest):
        """
        This is the HaproxySectionView API where you can update the HAProxy peers section.

        ---
        tags:
          - HAProxy peers section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of section to update.
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                type:
                  type: string
                  description: The type of the section.
                peers:
                  type: array
                  items:
                    type: object
                    properties:
                      name:
                        type: string
                        description: The name of the peer.
                      ip:
                        type: string
                        description: The IP address of the peer.
                      port:
                        type: string
                        description: The port of the peer.
                name:
                  type: string
                  description: The name of the section.
        responses:
          200:
            description: Haproxy section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().put(service, 'peers', section_name, server_id, body)

    @validate()
    def delete(self, service: Literal['haproxy'], section_name: str, server_id: Union[int, str]):
        """
        HaproxySectionView peers API

        This is the HaproxySectionView API where you can delete configurations of HAProxy peers sections.

        ---
        tags:
          - HAProxy peers section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this section belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: Server ID or IP address
          - name: section_name
            in: path
            type: string
            required: true
            description: The name of the section to fetch.
        responses:
          204:
            description: Haproxy section configuration.
        """
        return super().delete(service, 'peers', section_name, server_id)


class GlobalSectionView(HaproxySectionView):
    methods = ['GET', 'PUT']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate()
    def get(self, service: Literal['haproxy'], server_id: Union[int, str]):
        """
        GlobalSectionView API

        This is the GlobalSectionView API where you can get the global configuration of HAProxy.

        ---
        tags:
          - HAProxy global section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this global configuration belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: The server ID or server IP.
        responses:
          200:
            description: Global HAProxy configuration.
            schema:
              type: object
              properties:
                config:
                  type: object
                  properties:
                    chroot:
                      type: string
                      default: /var/lib/haproxy
                    daemon:
                      type: bool
                      default: 1
                    group:
                      type: string
                      default: haproxy
                    log:
                      type: array
                      items:
                        type: string
                        default: ['127.0.0.1 local', '127.0.0.1 local1 notice']
                    maxconn:
                      type: integer
                      default: 5000
                    pidfile:
                      type: string
                      default: /var/run/haproxy.pid
                    socket:
                      type: array
                      items:
                        type: string
                        default: ['*:1999 level admin', '/var/run/haproxy.sock mode 600 level admin', '/var/lib/haproxy/stats']
                    type:
                      type: string
                      default: global
                    user:
                      type: string
                      default: haproxy
                id:
                  type: integer
                name:
                  type: string
                server_id:
                  type: integer
                type:
                  type: string
          400:
            description: Invalid parameters.
          404:
            description: Global section not found.
          500:
            description: Internal server error.
        """
        return super().get(service, 'global', 'global', server_id)

    @validate(body=HaproxyGlobalRequest, query=GenerateConfigRequest)
    def put(self, service: Literal['haproxy'], server_id: Union[int, str], body: HaproxyGlobalRequest):
        """
        GlobalSectionView API

        This is the GlobalSectionView API where you can update the global configuration of HAProxy.

        ---
        tags:
          - HAProxy global section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this global configuration belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: The server ID or server IP.
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                chroot:
                  type: string
                  default: "/var/lib/haproxy"
                daemon:
                  type: integer
                  default: 1
                group:
                  type: string
                  default: "haproxy"
                log:
                  type: array
                  items:
                    type: string
                    default: ["127.0.0.1 local", "127.0.0.1 local1 notice"]
                maxconn:
                  type: integer
                  default: 5000
                pidfile:
                  type: string
                  default: "/var/run/haproxy.pid"
                socket:
                  type: array
                  items:
                    type: string
                    default: ["*:1999 level admin", "/var/run/haproxy.sock mode 600 level admin", "/var/lib/haproxy/stats"]
                user:
                  type: string
                  default: "haproxy"
                id:
                  type: integer
                  default: 20
                name:
                  type: string
                  default: "global"
                server_id:
                  type: integer
                  default: 1
                type:
                  type: string
                  default: "global"
        responses:
          200:
            description: Global HAProxy configuration successfully updated.
          400:
            description: Invalid parameters.
          404:
            description: Global section not found.
          500:
            description: Internal server error.
        """
        return super().put(service, 'global', 'global', server_id, body)


class DefaultsSectionView(HaproxySectionView):
    methods = ['GET', 'PUT']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate()
    def get(self, service: Literal['haproxy'], server_id: Union[int, str]):
        """
        DefaultsSectionView API

        This is the DefaultsSectionView API where you can get the defaults configuration of HAProxy.

        ---
        tags:
          - HAProxy defaults section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this defaults configuration belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: The server ID or server IP.
        responses:
          200:
            description: Defaults HAProxy configuration.
            schema:
              type: object
              properties:
                config:
                  type: object
                  properties:
                    log:
                      type: string
                      default: "global"
                    maxconn:
                      type: integer
                      default: 5000
                    option:
                      type: string
                      default: ""
                    retries:
                      type: integer
                      default: 3
                    timeout:
                      type: object
                      properties:
                        check:
                          type: integer
                          default: 10
                        client:
                          type: integer
                          default: 60
                        connect:
                          type: integer
                          default: 10
                        http_keep_alive:
                          type: integer
                          default: 10
                        http_request:
                          type: integer
                          default: 10
                        queue:
                          type: integer
                          default: 60
                        server:
                          type: integer
                          default: 60
                    type:
                      type: string
                      default: "defaults"
                id:
                  type: integer
                  default: 23
                name:
                  type: string
                  default: "defaults"
                server_id:
                  type: integer
                  default: 1
                type:
                  type: string
                  default: "defaults"
          400:
            description: Invalid parameters.
          404:
            description: Defaults section not found.
          500:
            description: Internal server error.
        """
        return super().get(service, 'defaults', 'defaults', server_id)

    @validate(body=HaproxyDefaultsRequest, query=GenerateConfigRequest)
    def put(self, service: Literal['haproxy'], server_id: Union[int, str], body: HaproxyDefaultsRequest):
        """
        DefaultsSectionView API

        This is the DefaultsSectionView API where you can update the defaults configuration of HAProxy.

        ---
        tags:
          - HAProxy defaults section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - haproxy
            description: The service to which this defaults configuration belongs.
          - name: server_id
            in: path
            type: string
            required: true
            description: The server ID or server IP.
          - name: body
            in: body
            required: true
            schema:
              type: object
              properties:
                log:
                  type: string
                  default: "global"
                maxconn:
                  type: integer
                  default: 5000
                option:
                  type: string
                  default: ""
                retries:
                  type: integer
                  default: 3
                timeout:
                  type: object
                  properties:
                    check:
                      type: integer
                      default: 10s
                    client:
                      type: integer
                      default: 60s
                    connect:
                      type: integer
                      default: 10s
                    http_keep_alive:
                      type: integer
                      default: 10s
                    http_request:
                      type: integer
                      default: 10s
                    queue:
                      type: integer
                      default: 60s
                    server:
                      type: integer
                      default: 60s
                type:
                  type: string
                  default: "defaults"
                id:
                  type: integer
                name:
                  type: string
                  default: "defaults"
                server_id:
                  type: integer
                type:
                  type: string
                  default: "defaults"
        responses:
          200:
            description: Defaults HAProxy configuration successfully updated.
          400:
            description: Invalid parameters.
          404:
            description: Defaults section not found.
          500:
            description: Internal server error.
        """
        return super().put(service, 'defaults', 'defaults', server_id, body)
