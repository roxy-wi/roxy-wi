from typing import Union

from flask import render_template, g, jsonify
from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required
from playhouse.shortcuts import model_to_dict
from pydantic import IPvAnyAddress

import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.common.common as common
import app.modules.db.udp as udp_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.server as server_sql
import app.modules.server.server as server_mod
import app.modules.service.udp as udp_mod
import app.modules.service.installation as service_mod
from app.middleware import get_user_params, check_services, page_for_admin, check_group
from app.modules.common.common_classes import SupportClass
from app.modules.roxywi.class_models import BaseResponse, IdResponse, UdpListenerRequest, GroupQuery, DomainName, DataStrResponse


class UDPListener(MethodView):
    method_decorators = ["GET", "POST", "PUT", "DELETE"]
    decorators = [jwt_required(), get_user_params(), check_services, check_group()]

    def __init__(self, is_api=True):
        self.is_api = is_api

    def get(self, service: str, listener_id: int):
        """
        Get information about a specific UDP listener.
        ---
        tags:
          - UDP listener
        parameters:
          - name: service
            in: path
            type: string
            required: true
            description: 'Can be only "udp"'
          - name: listener_id
            in: path
            type: integer
            required: true
            description: The listener's identifier
        responses:
          200:
            description: Listener configuration returned successfully
            schema:
              type: object
              properties:
                check_enabled:
                  type: integer
                cluster_id:
                  type: string
                config:
                  type: array
                  items:
                    type: object
                    properties:
                      backend_ip:
                        type: string
                        description: The IP address of the backend server
                      port:
                        type: integer
                        description: Port number on which the backend server listens for requests
                      weight:
                        type: integer
                        description: Weight assigned to the backend server
                delay_before_retry:
                  type: integer
                delay_loop:
                  type: integer
                description:
                  type: string
                group_id:
                  type: integer
                id:
                  type: integer
                lb_algo:
                  type: string
                name:
                  type: string
                port:
                  type: integer
                retry:
                  type: integer
                server_id:
                  type: integer
                vip:
                  type: string
          default:
            description: Unexpected error
            """
        if self.is_api:
            if listener_id:
                try:
                    listener_config = udp_mod.get_listener_config(listener_id)
                    listener_config['status'] = udp_mod.check_is_listener_active(listener_id)
                except Exception as e:
                    return roxywi_common.handler_exceptions_for_json_data(e, 'Listener not found')
                return jsonify(listener_config)
        else:
            if not listener_id:
                kwargs = {
                    'lang': g.user_params['lang'],
                    'clusters': ha_sql.select_clusters(g.user_params['group_id']),
                    'is_needed_tool': common.is_tool('ansible'),
                    'user_subscription': roxywi_common.return_user_subscription()
                }
                return render_template('udp/listeners.html', **kwargs)
            else:
                listener = udp_sql.get_listener(listener_id)
                cluster = dict()
                server = dict()
                if listener.cluster_id:
                    cluster = ha_sql.select_cluster(listener.cluster_id)
                elif listener.server_id:
                    server = server_sql.get_server(listener.server_id)
                kwargs = {
                    'clusters': cluster,
                    'listener': listener,
                    'server': server,
                    'lang': g.user_params['lang'],
                }
                return render_template('udp/listener.html', **kwargs)

    @validate(body=UdpListenerRequest)
    def post(self, service: str, body: UdpListenerRequest):
        """
        This endpoint allows to create a new UDP listener.
        ---
        tags:
          - UDP listener
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "udp"'
            required: true
            type: 'string'
          - in: body
            name: body
            required: true
            schema:
              required:
                - config
                - name
                - port
                - lb_algo
                - vip
              type: object
              properties:
                config:
                  type: array
                  items:
                    type: object
                    properties:
                      backend_ip:
                        type: string
                        description: The IP address of the backend server
                      port:
                        type: integer
                        description: Port number on which the backend server listens for requests
                      weight:
                        type: integer
                        description: Weight assigned to the backend server
                name:
                  type: string
                cluster_id:
                  type: integer
                  description: Cluster ID where the UDP listener is located. Must be determined if server_id empty
                server_id:
                  type: integer
                  description: Standalone mode. Server ID where the UDP listener is located. Must be determined if cluster_id empty
                group_id:
                  type: string
                port:
                  type: string
                lb_algo:
                  type: string
                  description: "'rr': 'Round robin', 'wrr': 'Weighted Round Robin', 'lc': 'Least Connection', 'wlc': 'Weighted Least Connection', 'sh': 'Source Hashing', 'dh': 'Destination Hashing', 'lblc': 'Locality-Based Least Connection'"
                  schema:
                    enum: [rr, wrr, lc, wlc, sh, dh, wlc, lblc]
                check_enabled:
                  type: integer
                  default: 1
                  description: Enable backend servers checking
                delay_before_retry:
                  type: integer
                  default: 10
                  description: Delay between two successive retries
                delay_loop:
                  type: integer
                  default: 10
                  description: Specify in seconds the interval between checks
                retry:
                  type: integer
                  default: 3
                  description: Maximum number of retries before mark a backend server as down
                description:
                  type: string
                vip:
                  type: string
                  description: IP address of the UDP listener binding, if Standalone mode. VIP address of the UDP listener binding, if HA Cluster mode
                reconfigure:
                  type: boolean
                  description: If 1, reconfigure UDP listener. If 0, just save UDP listener without configuration on servers
                is_checker:
                  type: boolean
                  description: Should be Checker service check this UDP listener?
        responses:
          201:
            description: UDP listener created successfully
          400:
            description: Invalid request data
          default:
            description: Unexpected error
        """
        roxywi_auth.page_for_admin(level=3)
        try:
            listener_id = udp_sql.insert_listener(**body.model_dump(mode='json', exclude={'reconfigure'}))
            roxywi_common.logging(listener_id, f'UDP listener {body.name} has been created', keep_history=1,
                              roxywi=1, service='UDP Listener')
            if body.reconfigure:
                task_id = self._reconfigure(listener_id, 'install')
                return jsonify({"status": "accepted", "tasks_ids": [task_id], 'id': listener_id}), 202
            return IdResponse(id=listener_id).model_dump(mode='json')
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot create UDP listener')

    @validate(body=UdpListenerRequest)
    def put(self, service: str, listener_id: int, body: UdpListenerRequest):
        """
        This endpoint allows to update a UDP listener.
        ---
        tags:
          - UDP listener
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "udp"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'listener_id'
            description: 'ID of the UDP listener'
            required: true
            type: 'integer'
          - in: body
            name: body
            required: true
            schema:
              required:
                - config
                - name
                - port
                - lb_algo
                - vip
              type: object
              properties:
                config:
                  type: array
                  items:
                    type: object
                    properties:
                      backend_ip:
                        type: string
                        description: The IP address of the backend server
                      port:
                        type: integer
                        description: Port number on which the backend server listens for requests
                      weight:
                        type: integer
                        description: Weight assigned to the backend server
                name:
                  type: string
                cluster_id:
                  type: integer
                  description: Cluster ID where the UDP listener is located. Must be determined if server_id empty
                server_id:
                  type: integer
                  description: Standalone mode. Server ID where the UDP listener is located. Must be determined if cluster_id empty
                group_id:
                  type: string
                port:
                  type: string
                lb_algo:
                  type: string
                  description: "'rr': 'Round robin', 'wrr': 'Weighted Round Robin', 'lc': 'Least Connection', 'wlc': 'Weighted Least Connection', 'sh': 'Source Hashing', 'dh': 'Destination Hashing', 'lblc': 'Locality-Based Least Connection'"
                  schema:
                    enum: [rr, wrr, lc, wlc, sh, dh, wlc, lblc]
                check_enabled:
                  type: integer
                  default: 1
                  description: Enable backend servers checking
                delay_before_retry:
                  type: integer
                  default: 10
                  description: Delay between two successive retries
                delay_loop:
                  type: integer
                  default: 10
                  description: Specify in seconds the interval between checks
                retry:
                  type: integer
                  default: 3
                  description: Maximum number of retries before mark a backend server as down
                description:
                  type: string
                vip:
                  type: string
                  description: IP address of the UDP listener binding, if Standalone mode. VIP address of the UDP listener binding, if HA Cluster mode
                reconfigure:
                  type: boolean
                  description: If 1, reconfigure UDP listener. If 0, just save UDP listener without configuration on servers
                is_checker:
                  type: boolean
                  description: Should be Checker service check this UDP listener?
        responses:
          201:
            description: UDP listener created successfully
          400:
            description: Invalid request data
          default:
            description: Unexpected error
        """
        roxywi_auth.page_for_admin(level=3)
        try:
            udp_sql.update_listener(listener_id, **body.model_dump(mode='json', exclude={'reconfigure'}))
            roxywi_common.logging(listener_id, f'UDP listener {body.name} has been updated', keep_history=1,
                                  roxywi=1, service='UDP Listener')
            if body.reconfigure:
                self._reconfigure(listener_id, 'install')
            return BaseResponse().model_dump(mode='json')
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot update UDP listener')

    def delete(self, service: str, listener_id: int):
        """
        Delete a UDP listener
        ---
        tags:
          - UDP listener
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "udp"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'listener_id'
            description: 'ID of the UDP listener'
            required: true
            type: 'integer'
        responses:
          204:
            description: UDP listener deletion successful
        """
        roxywi_auth.page_for_admin(level=3)
        try:
            self._reconfigure(listener_id, 'uninstall')
            roxywi_common.logging(listener_id, f'UDP listener has been deleted {listener_id}', roxywi=1, keep_history=1, login=1, service='UDP listener')
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot create inventory for UDP listener deleting {listener_id}')
        try:
            udp_sql.delete_listener(listener_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot delete UDP listener {listener_id}')

    @staticmethod
    def _reconfigure(listener_id, action):
        try:
            inv, server_ips = service_mod.generate_udp_inv(listener_id, action)
        except Exception as e:
            raise Exception(e)
        try:
            task_id = service_mod.run_ansible_thread(inv, server_ips, 'udp', 'UDP listener')
            return task_id
        except Exception as e:
            raise Exception(f'Cannot {action} UDP listener: {e}')


class UDPListeners(MethodView):
    method_decorators = ["GET"]
    decorators = [jwt_required(), get_user_params(), check_services, check_group()]

    @validate(query=GroupQuery)
    def get(self, service: str, query: GroupQuery):
        """
        Get information about a specific UDP listener.
        ---
        tags:
          - UDP listener
        parameters:
          - name: service
            in: path
            type: string
            required: true
            description: 'Can be only "udp"'
          - name: group_id
            in: query
            type: integer
            required: false
            description: The group's identifier. Only accessible by superAdmin role.
        responses:
          200:
            description: Listener configuration returned successfully
            schema:
              type: array
              items:
                type: object
                properties:
                  check_enabled:
                    type: integer
                  cluster_id:
                    type: string
                  config:
                    type: array
                    items:
                      type: object
                      properties:
                        backend_ip:
                          type: string
                          description: The IP address of the backend server
                        port:
                          type: integer
                          description: Port number on which the backend server listens for requests
                        weight:
                          type: integer
                          description: Weight assigned to the backend server
                  delay_before_retry:
                    type: integer
                  delay_loop:
                    type: integer
                  description:
                    type: string
                  group_id:
                    type: integer
                  id:
                    type: integer
                  lb_algo:
                    type: string
                  name:
                    type: string
                  port:
                    type: integer
                  retry:
                    type: integer
                  server_id:
                    type: integer
                  vip:
                    type: string
          default:
            description: Unexpected error
        """
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot get UDP listeners')
        try:
            listeners = udp_sql.select_listeners(group_id)
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot get UDP listeners')
        return jsonify([model_to_dict(listener, recurse=False) for listener in listeners])


class UDPListenerActionView(MethodView):
    methods = ['GET']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @staticmethod
    def get(service: str, listener_id: int, action: str):
        """
        This endpoint performs a specified action on a certain UDP listener.
        ---
        tags:
          - UDP listener
        parameters:
          - in: path
            name: service
            required: true
            type: 'string'
            description: Can be only "udp"
          - in: path
            name: listener_id
            type: 'integer'
            required: true
            description: The ID af the UDP listener
          - in: path
            name: action
            type: 'string'
            required: true
            description: The action to be performed on the service (start, stop, reload, restart)
        responses:
          200:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            udp_mod.listener_actions(listener_id, action, g.user_params['group_id'])
            roxywi_common.logging(listener_id, f'UDP listener {listener_id} has been {action}ed', roxywi=1,
                                  keep_history=1, login=1, service='UDP listener')
            return BaseResponse().model_dump(mode='json')
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot {action} listener')


class UDPListenerBackendStatusView(MethodView):
    methods = ['GET']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @staticmethod
    @validate()
    def get(service: str, listener_id: int, backend_ip: Union[IPvAnyAddress, DomainName]):
        """
        UDP Listener Backend Status View

        ---
        tags:
            - UDP listener
        parameters:
            - in: path
              name: listener_id
              required: true
              description: The ID of the UDP listener.
              type: integer
            - in: path
              name: backend_ip
              required: true
              description: The IP address of the backend server.
              type: string
        responses:
            200:
                description: Success. Returns the backend status for the given UDP listener.
                content:
                  application/json:
                    schema:
                      type: object
                      properties:
                        status:
                          type: string
                          description: The backend status (e.g., 'yes', 'no').
            400:
                description: Bad request. Invalid listener_id or backend_ip.
            404:
                description: Not found. The specified UDP listener or backend was not found.
        """
        try:
            listener = udp_sql.get_listener(listener_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get UDP listeners')

        if listener.cluster_id:
            cluster = ha_sql.get_cluster(listener.cluster_id)
            router_id = ha_sql.get_router_id(cluster.id, 1)
            slaves = ha_sql.select_cluster_slaves(cluster.id, router_id)

            for slave in slaves:
                server_ip = server_sql.get_server(slave[0]).ip
        elif listener.server_id:
            server_ip = server_sql.get_server(listener.server_id).ip
        else:
            return roxywi_common.handler_exceptions_for_json_data(Exception(''), 'Cannot get UDP listeners')

        cmd = (f"sudo kill -s $(keepalived --signum=DATA) $(cat /var/run/keepalived-udp-{listener_id}.pid) && "
               f"sudo grep {backend_ip} -A 3 /tmp/keepalived_check.data |grep Up |awk '{{print $3}}'")
        status = server_mod.ssh_command(server_ip, cmd)
        status = status.replace('\r\n', '')
        return DataStrResponse(data=status).model_dump(mode='json')


class UdpListenerCheckerView(MethodView):
    methods = ['POST']
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @validate(query=GroupQuery)
    def post(self, service: str, listener_id: int, is_checker: int, query: GroupQuery):
        try:
            _ = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot get UDP listeners')
        try:
            udp_sql.get_listener(listener_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get UDP listeners')

        try:
            udp_sql.update_listener(listener_id, is_checker=is_checker)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update checker settings on UDP listener')

        return BaseResponse().model_dump(mode='json'), 201
