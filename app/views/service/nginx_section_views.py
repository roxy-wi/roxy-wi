import os
from typing import Union, Literal

from flask.views import MethodView
from flask_pydantic import validate
from flask import jsonify, g
from flask_jwt_extended import jwt_required
from playhouse.shortcuts import model_to_dict

import app.modules.db.sql as sql
import app.modules.db.add as add_sql
import app.modules.db.server as server_sql
import app.modules.server.ssh as mod_ssh
import app.modules.config.config as config_mod
import app.modules.config.common as config_common
import app.modules.service.installation as service_mod
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.db.db_model import Server
from app.modules.roxywi.class_models import BaseResponse, DataStrResponse, NginxUpstreamRequest, IdDataStrResponse, \
    ErrorResponse, GenerateConfigRequest, NginxProxyPassRequest
from app.modules.common.common_classes import SupportClass


class NginxSectionView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @staticmethod
    def get(service: Literal['nginx'], section_type: str, section_name: str, server_id: Union[int, str]):
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            server_sql.get_server_with_group(server_id, g.user_params['group_id'])
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find a server')

        try:
            section = add_sql.get_section(server_id, section_type, section_name, service)
            output = {'server_id': section.server_id.server_id, **model_to_dict(section, recurse=False),
                      'id': f'{server_id}-{section_name}'}
            output.update(section.config)
            return jsonify(output)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get NGINX section')

    def post(self,
             service: Literal['nginx'],
             section_type: str,
             server_id: Union[int, str],
             body: Union[NginxUpstreamRequest, NginxProxyPassRequest],
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
            cfg = '/tmp/nginx-generated-config.conf'
            os.system(f'touch {cfg}')
            inv = service_mod.generate_section_inv(body.model_dump(mode='json'), cfg, service)

            try:
                output = service_mod.run_ansible_locally(inv, 'nginx_section')
                if len(output['failures']) > 0 or len(output['dark']) > 0:
                    raise Exception('Cannot create NGINX section. Check Apache error log')
            except Exception as e:
                return roxywi_common.handler_exceptions_for_json_data(e, f'Cannot create NGINX section: {e}')
            try:
                with open(cfg, 'r') as file:
                    conf = file.read()
            except Exception as e:
                raise Exception(f'error: Cannot read config file: {e}')
            try:
                os.remove(cfg)
            except Exception:
                pass
            return DataStrResponse(data=conf).model_dump(mode='json'), 200

        try:
            output = self._edit_config(service, server, body, 'create')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create NGINX section')

        if 'Fatal' in output or 'error' in output:
            return ErrorResponse(error=output).model_dump(mode='json'), 500

        try:
            add_sql.insert_new_section(server_id, section_type, body.name, body, service)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot add NGINX section')

        return IdDataStrResponse(data=output, id=f'{server_id}-{body.name}').model_dump(mode='json'), 201

    def put(self,
            service: Literal['nginx'],
            section_type: str,
            section_name: str,
            server_id: Union[int, str],
            body: Union[NginxUpstreamRequest, NginxProxyPassRequest]
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
            return ErrorResponse(error=output).model_dump(mode='json'), 500
        else:
            try:
                add_sql.update_section(server_id, section_type, section_name, body, service)
            except Exception as e:
                return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update NGINX section')

        return DataStrResponse(data=output).model_dump(mode='json'), 201

    def delete(self, service: Literal['nginx'], section_type: str, section_name: str, server_id: Union[int, str]):
        try:
            server_id = SupportClass().return_server_ip_or_id(server_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        try:
            server = server_sql.get_server_with_group(server_id, g.user_params['group_id'])
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find a server')

        try:
            config_file_name = self._create_config_path(service, section_type, section_name)
            with mod_ssh.ssh_connect(server.ip) as ssh:
                ssh.remove_sftp(config_file_name)
            add_sql.delete_section(server_id, section_type, section_name, service)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete NGINX section')

        return BaseResponse().model_dump(mode='json'), 204

    @staticmethod
    def _create_config_path(service: str, config_type: str, name: str) -> str:
        service_dir = sql.get_setting(f'{service}_dir')
        if config_type == 'upstream':
            config_file_name = f'{service_dir}/conf.d/upstream_{name}.conf'
        else:
            config_file_name = f'{service_dir}/sites-enabled/proxy-pass_{name}.conf'
        return config_file_name

    def _edit_config(self, service, server: Server, body: NginxUpstreamRequest, action: Literal['create', 'delete'], **kwargs) -> str:
        cfg = config_common.generate_config_path(service, server.ip)
        print('cfg', cfg)
        config_file_name = self._create_config_path(service, body.type, body.name)

        if action == 'create':
            inv = service_mod.generate_section_inv(body.model_dump(mode='json'), cfg, service)
        else:
            inv = service_mod.generate_section_inv_for_del(cfg, kwargs.get('section_type'), kwargs.get('section_name'))

        try:
            config_mod.get_config(server.ip, cfg, service=service, config_file_name=config_file_name)
        except Exception as e:
            raise e

        os.system(f'mv {cfg} {cfg}.old')

        try:
            output = service_mod.run_ansible_locally(inv, 'nginx_section')
        except Exception as e:
            raise e

        if len(output['failures']) > 0 or len(output['dark']) > 0:
            raise Exception('Cannot create NGINX section. Check Apache error log')

        if body:
            if body.action:
                action = str(body.action)
        else:
            action = 'save'

        output = config_mod.master_slave_upload_and_restart(server.ip, cfg, action, service, config_file_name=config_file_name, oldcfg=f'{cfg}.old')

        return output


class UpstreamSectionView(NginxSectionView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def __init__(self):
        self.section_type = 'upstream'

    @validate()
    def get(self, service: Literal['nginx'], section_name: str, server_id: Union[int, str]):
        """
        NginxUpstreamView API

        This is the NginxUpstreamView API where you can get configurations of NGINX sections.

        ---
        tags:
          - NGINX upstream section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
            description: NGINX upstream configuration.
            schema:
              type: object
              properties:
                config:
                  type: object
                  properties:
                    backend_servers:
                      type: array
                      items:
                        type: object
                        properties:
                          server:
                            type: string
                          port:
                            type: integer
                          max_fails:
                            type: integer
                          fail_timeout:
                            type: integer
                    name:
                      type: string
                    balance:
                      type: string
                    keepalive:
                      type: integer
                id:
                  type: string
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
        return super().get(service, self.section_type, section_name, server_id)

    @validate(body=NginxUpstreamRequest, query=GenerateConfigRequest)
    def post(self,
             service: Literal['nginx'],
             server_id: Union[int, str],
             body: NginxUpstreamRequest,
             query: GenerateConfigRequest
             ):
        """
        NginxUpstreamView API

        This is the NginxUpstreamView API where you can create NGINX sections.

        ---
        tags:
          - NGINX upstream section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
                backend_servers:
                  type: array
                  items:
                    type: object
                    properties:
                      server:
                        type: string
                      port:
                        type: integer
                      max_fails:
                        type: integer
                      fail_timeout:
                        type: integer
                name:
                  type: string
                  description: The name of the upstream
                balance:
                  type: string
                  description: Could be 'round_robin', 'ip_hash', 'least_conn' or 'random'
                  default: round_robin
                keepalive:
                  type: integer
                  default: 32
        responses:
          200:
            description: NGINX section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().post(service, self.section_type, server_id, body, query)

    @validate(body=NginxUpstreamRequest)
    def put(self,
            service: Literal['nginx'],
            server_id: Union[int, str],
            section_name: str,
            body: NginxUpstreamRequest,
            query: GenerateConfigRequest
            ):
        """
        This is the NginxUpstreamView API where you can update the NGINX sections.

        ---
        tags:
          - NGINX upstream section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
                backend_servers:
                  type: array
                  items:
                    type: object
                    properties:
                      server:
                        type: string
                      port:
                        type: integer
                      max_fails:
                        type: integer
                      fail_timeout:
                        type: integer
                name:
                  type: string
                  description: The name of the upstream to update.
                balance:
                  type: string
                  description: Could be 'round_robin', 'ip_hash', 'least_conn' or 'random'
                  default: round_robin
                keepalive:
                  type: integer
                  default: 32
        responses:
          200:
            description: NGINX section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().put(service, self.section_type, section_name, server_id, body)

    @validate()
    def delete(self, service: Literal['nginx'], section_name: str, server_id: Union[int, str]):
        """
        NginxUpstreamView sections API

        This is the NginxUpstreamView API where you can delete configurations of NGINX sections.

        ---
        tags:
          - NGINX upstream section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
            description: NGINX section configuration.
        """
        return super().delete(service, self.section_type, section_name, server_id)


class ProxyPassSectionView(NginxSectionView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def __init__(self):
        self.section_type = 'proxy_pass'

    @validate()
    def get(self, service: Literal['nginx'], section_name: str, server_id: Union[int, str]):
        """
        NginxProxyPassView API

        This is the NginxProxyPassView API where you can get configurations of NGINX sections.

        ---
        tags:
          - NGINX proxy_pass section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
            description: Proxy Pass Section details retrieved successfully.
            schema:
              type: object
              properties:
                compression:
                  type: boolean
                  description: Indicates whether compression is enabled.
                compression_level:
                  type: integer
                  description: Specifies the compression level (from 1 to 9).
                compression_min_length:
                  type: integer
                  description: Minimum response size in bytes for compression to apply.
                compression_types:
                  type: string
                  description: MIME types (space-separated) that compression applies to.
                id:
                  type: string
                  description: Unique ID of the proxy pass section.
                locations:
                  type: array
                  items:
                    type: object
                    properties:
                      location:
                        type: string
                        description: Path of the location block (e.g., `/`).
                      headers:
                        type: array
                        description: List of headers for the location.
                        items:
                          type: object
                      proxy_connect_timeout:
                        type: integer
                        description: Timeout value for connecting to the upstream server (in seconds).
                      proxy_read_timeout:
                        type: integer
                        description: Timeout for reading data from the upstream server (in seconds).
                      proxy_send_timeout:
                        type: integer
                        description: Timeout for sending data to the upstream server (in seconds).
                      upstream:
                        type: string
                        description: Name of the upstream server.
                name:
                  type: string
                  description: Name of the proxy pass configuration.
                port:
                  type: integer
                  description: Port on which this proxy pass runs.
                scheme:
                  type: string
                  enum:
                    - http
                    - https
                  description: Protocol used by the proxy.
                server_id:
                  type: integer
                  description: ID of the associated server.
                ssl_crt:
                  type: string
                  description: SSL certificate file name.
                ssl_key:
                  type: string
                  description: SSL private key file name.
                ssl_offloading:
                  type: boolean
                  description: Indicates whether SSL offloading is enabled.
                type:
                  type: string
                  enum:
                    - proxy_pass
                  description: Section type (e.g., "proxy_pass").
          400:
            description: Invalid parameters.
          404:
            description: Section not found.
          500:
            description: Internal server error.
        """
        return super().get(service, self.section_type, section_name, server_id)

    @validate(body=NginxProxyPassRequest, query=GenerateConfigRequest)
    def post(self,
             service: Literal['nginx'],
             server_id: Union[int, str],
             body: NginxProxyPassRequest,
             query: GenerateConfigRequest
             ):
        """
        NginxProxyPassView API

        This is the NginxProxyPassView API where you can create NGINX sections.

        ---
        tags:
          - NGINX proxy_pass section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
              required:
                - locations
                - name
                - scheme
                - port
              properties:
                locations:
                  type: array
                  description: List of locations associated with this proxy pass section.
                  items:
                    type: object
                    required:
                      - location
                      - proxy_connect_timeout
                      - proxy_read_timeout
                      - proxy_send_timeout
                      - upstream
                    properties:
                      location:
                        type: string
                        description: Path of the location block (e.g., `/`).
                        default: /
                      proxy_connect_timeout:
                        type: string
                        description: Timeout value for connecting to the upstream server (in seconds).
                        default: 60
                      proxy_read_timeout:
                        type: string
                        description: Timeout for reading data from the upstream server (in seconds).
                        default: 60
                      proxy_send_timeout:
                        type: string
                        description: Timeout for sending data to the upstream server (in seconds).
                        default: 60
                      headers:
                        type: array
                        description: List of headers for the location (currently empty).
                        items:
                          type: object
                          required:
                            - action
                            - name
                          properties:
                            action:
                              type: string
                              description: Action to perform on the header (e.g., "add_header").
                              enum:
                                - add_header
                                - proxy_set_header
                                - proxy_hide_header
                            name:
                              type: string
                              description: Name of the header.
                              example: X-Real-IP
                            value:
                              type: string
                              description: Value of the header.
                      upstream:
                        type: string
                        description: Name of the upstream server.
                name:
                  type: string
                  description: Domain name or IP of the proxy pass section.
                scheme:
                  type: string
                  enum:
                    - http
                    - https
                  description: Scheme (protocol) for the proxy pass section.
                port:
                  type: integer
                  description: Port number on which the proxy pass section operates.
                ssl_offloading:
                  type: boolean
                  description: Indicates whether SSL offloading is enabled.
                  default: false
                ssl_key:
                  type: string
                  description: SSL private key file name. Need if scheme is https.
                ssl_crt:
                  type: string
                  description: SSL certificate file name. Need if scheme is https
                compression_types:
                  type: string
                  description: Space-separated list of MIME types to be compressed.
                  default: text/plain text/css application/json application/javascript text/xml
                compression_min_length:
                  type: string
                  description: Minimum response size in bytes for compression to apply.
                  default: 1024
                compression_level:
                  type: string
                  description: The compression level (e.g., 1 to 9).
                  default: 6
        responses:
          200:
            description: NGINX section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().post(service, self.section_type, server_id, body, query)

    @validate(body=NginxProxyPassRequest)
    def put(self,
            service: Literal['nginx'],
            server_id: Union[int, str],
            section_name: str,
            body: NginxProxyPassRequest,
            query: GenerateConfigRequest
            ):
        """
        This is the NginxProxyPassView API where you can update the NGINX sections.

        ---
        tags:
          - NGINX proxy_pass section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
              required:
                - locations
                - name
                - scheme
                - port
              properties:
                locations:
                  type: array
                  description: List of locations associated with this proxy pass section.
                  items:
                    type: object
                    required:
                      - location
                      - proxy_connect_timeout
                      - proxy_read_timeout
                      - proxy_send_timeout
                      - upstream
                    properties:
                      location:
                        type: string
                        description: Path of the location block (e.g., `/`).
                        default: /
                      proxy_connect_timeout:
                        type: string
                        description: Timeout value for connecting to the upstream server (in seconds).
                        default: 60
                      proxy_read_timeout:
                        type: string
                        description: Timeout for reading data from the upstream server (in seconds).
                        default: 60
                      proxy_send_timeout:
                        type: string
                        description: Timeout for sending data to the upstream server (in seconds).
                        default: 60
                      headers:
                        type: array
                        description: List of headers for the location (currently empty).
                        items:
                          type: object
                          required:
                            - action
                            - name
                          properties:
                            action:
                              type: string
                              description: Action to perform on the header (e.g., "add_header").
                              enum:
                                - add_header
                                - proxy_set_header
                                - proxy_hide_header
                            name:
                              type: string
                              description: Name of the header.
                              example: X-Real-IP
                            value:
                              type: string
                              description: Value of the header.
                      upstream:
                        type: string
                        description: Name of the upstream server.
                name:
                  type: string
                  description: Domain name or IP of the proxy pass section.
                scheme:
                  type: string
                  enum:
                    - http
                    - https
                  description: Scheme (protocol) for the proxy pass section.
                port:
                  type: integer
                  description: Port number on which the proxy pass section operates.
                ssl_offloading:
                  type: boolean
                  description: Indicates whether SSL offloading is enabled.
                  default: false
                ssl_key:
                  type: string
                  description: SSL private key file name. Need if scheme is https.
                ssl_crt:
                  type: string
                  description: SSL certificate file name. Need if scheme is https
                compression_types:
                  type: string
                  description: Space-separated list of MIME types to be compressed.
                  default: text/plain text/css application/json application/javascript text/xml
                compression_min_length:
                  type: string
                  description: Minimum response size in bytes for compression to apply.
                  default: 1024
                compression_level:
                  type: string
                  description: The compression level (e.g., 1 to 9).
                  default: 6
        responses:
          200:
            description: NGINX section successfully created.
          400:
            description: Invalid parameters.
          500:
            description: Internal server error.
        """
        return super().put(service, self.section_type, section_name, server_id, body)

    @validate()
    def delete(self, service: Literal['nginx'], section_name: str, server_id: Union[int, str]):
        """
        NginxProxyPassView sections API

        This is the NginxProxyPassView API where you can delete configurations of NGINX sections.

        ---
        tags:
          - NGINX proxy_pass section
        parameters:
          - name: service
            in: path
            type: string
            required: true
            enum:
              - nginx
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
            description: NGINX section configuration.
        """
        return super().delete(service, self.section_type, section_name, server_id)
