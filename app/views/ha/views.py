from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required
from flask import render_template, request, jsonify, g
from playhouse.shortcuts import model_to_dict

import app.modules.db.ha_cluster as ha_sql
import app.modules.db.service as service_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.common.common as common
import app.modules.service.ha_cluster as ha_cluster
import app.modules.service.installation as service_mod
from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.roxywi.class_models import BaseResponse, IdResponse, HAClusterRequest, HAClusterVIP


class HAView(MethodView):
    methods = ["GET", "POST", "PUT", "DELETE"]
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def __init__(self):
        self.group_id = g.user_params['group_id']

    def get(self, service: str, cluster_id: int):
        """
        This endpoint retrieves information about the specified HA Cluster.
        ---
        tags:
          - HA Cluster
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to retrieve information from.'
            required: true
            type: 'integer'
        responses:
          200:
            description: HA details retrieved successfully
            schema:
              type: object
              properties:
                description:
                  type: string
                  description: Description of the HA
                eth:
                  type: string
                  description: Ethernet interface
                group_id:
                  type: integer
                  description: Group ID
                id:
                  type: integer
                  description: ID of the HA
                name:
                  type: string
                  description: Name of the listener
                pos:
                  type: integer
                  description: Position
                return_master:
                  type: integer
                  description: Return master flag
                servers:
                  type: array
                  items:
                    type: object
                    properties:
                      eth:
                        type: string
                        description: Ethernet interface
                      id:
                        type: integer
                        description: Server ID
                      master:
                        type: integer
                        description: Master flag
                services:
                  type: object
                  properties:
                    apache:
                      type: object
                      properties:
                        docker:
                          type: integer
                          description: Docker flag for Apache
                        enabled:
                          type: integer
                          description: Enabled flag for Apache
                    haproxy:
                      type: object
                      properties:
                        docker:
                          type: integer
                          description: Docker flag for HAProxy
                        enabled:
                          type: integer
                          description: Enabled flag for HAProxy
                    nginx:
                      type: object
                      properties:
                        docker:
                          type: integer
                          description: Docker flag for NGINX
                        enabled:
                          type: integer
                          description: Enabled flag for NGINX
                syn_flood:
                  type: integer
                  description: SYN Flood protection flag
                use_src:
                  type: integer
                  description: Use source flag
                vip:
                  type: string
                  description: Virtual IP address
                virt_server:
                  type: integer
                  description: Virtual server flag
        """
        if not cluster_id:
            if request.method == 'GET':
                kwargs = {
                    'clusters': ha_sql.select_clusters(self.group_id),
                    'is_needed_tool': common.is_tool('ansible'),
                    'user_subscription': roxywi_common.return_user_subscription(),
                    'lang': g.user_params['lang'],
                }

                return render_template('ha_cluster.html', **kwargs)
        else:
            settings = {}
            clusters = ha_sql.select_cluster(cluster_id)
            router_id = ha_sql.get_router_id(cluster_id, default_router=1)
            slaves = ha_sql.select_cluster_slaves(cluster_id, router_id)
            cluster_services = ha_sql.select_cluster_services(cluster_id)
            vip = ha_sql.select_cluster_vip(cluster_id, router_id)
            is_virt = ha_sql.check_ha_virt(vip.id)
            if vip.use_src:
                use_src = 1
            else:
                use_src = 0

            for cluster in clusters:
                settings = model_to_dict(cluster)
            settings.setdefault('vip', vip.vip)
            settings.setdefault('virt_server', is_virt)
            settings.setdefault('use_src', use_src)
            settings.setdefault('return_master', vip.return_master)
            settings['servers'] = []
            settings['services'] = {
                'haproxy': {
                    'enabled': 0,
                    'docker': 0
                },
                'nginx': {
                    'enabled': 0,
                    'docker': 0
                },
                'apache': {
                    'enabled': 0,
                    'docker': 0
                }
            }

            for slave in slaves:
                server_id = slave[0]
                if slave[31]:
                    settings.setdefault('eth', slave[32])
                server_settings = {'id': server_id, 'eth': slave[32], 'master': slave[31]}
                settings['servers'].append(server_settings)

            for c_s in cluster_services:
                is_dockerized = int(service_sql.select_service_setting(server_id, c_s.service_id, 'dockerized'))
                if int(c_s.service_id) == 1:
                    settings['services']['haproxy'] = {'enabled': 1, 'docker': is_dockerized}
                if int(c_s.service_id) == 2:
                    settings['services']['nginx'] = {'enabled': 1, 'docker': is_dockerized}
                if int(c_s.service_id) == 4:
                    settings['services']['apache'] = {'enabled': 1, 'docker': is_dockerized}

            return jsonify(settings)

    @validate(body=HAClusterRequest)
    def post(self, service: str, body: HAClusterRequest):
        """
        This endpoint allows to create a new HA cluster.
        ---
        tags:
          - HA Cluster
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: body
            name: body
            required: true
            schema:
              required:
                - name
                - services
              type: object
              properties:
                servers:
                  type: 'array'
                  description: Must be at least 2 servers. One of them must be master = 1
                  items:
                    type: 'object'
                    properties:
                      eth:
                        type: 'string'
                        description: Ethernet interface to bind VIP address
                      master:
                        type: 'integer'
                      id:
                        type: 'integer'
                name:
                  type: string
                description:
                  type: string
                vip:
                  type: string
                virt_server:
                  type: integer
                return_to_master:
                  type: string
                syn_flood:
                  type: integer
                use_src:
                  type: integer
                services:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      enabled:
                        type: integer
                      docker:
                        type: integer
                router_id:
                  type: integer
        responses:
          201:
            description: HA cluster created successfully
          400:
            description: Invalid request data
          default:
            description: Unexpected error
        """
        try:
            cluster_id = ha_cluster.create_cluster(body, self.group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create cluster')

        if body.reconfigure:
            try:
                self._install_service(body, cluster_id)
            except Exception as e:
                return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot reconfigure cluster')

        return IdResponse(id=cluster_id).model_dump(mode='json'), 201

    @validate(body=HAClusterRequest)
    def put(self, service: str, cluster_id: int, body: HAClusterRequest):
        """
        This endpoint allows to update a HA cluster.
        ---
        tags:
          - HA Cluster
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to update'
            required: true
            type: 'integer'
          - in: body
            name: body
            required: true
            schema:
              required:
                - name
                - services
              type: object
              properties:
                servers:
                  type: 'array'
                  description: Must be at least 2 servers. One of them must be master = 1
                  items:
                    type: 'object'
                    properties:
                      eth:
                        type: 'string'
                        description: Ethernet interface to bind VIP address
                      master:
                        type: 'integer'
                      id:
                        type: 'integer'
                name:
                  type: string
                description:
                  type: string
                vip:
                  type: string
                virt_server:
                  type: integer
                return_to_master:
                  type: string
                syn_flood:
                  type: integer
                use_src:
                  type: integer
                services:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      enabled:
                        type: integer
                      docker:
                        type: integer
        responses:
          201:
            description: HA cluster updated successfully
          400:
            description: Invalid request data
          404:
             description: HA cluster not found
          default:
            description: Unexpected error
        """
        try:
            ha_cluster.update_cluster(body, cluster_id, self.group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update cluster')

        if body.reconfigure:
            try:
                self._install_service(body, cluster_id)
            except Exception as e:
                return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot reconfigure cluster')

        return BaseResponse().model_dump(mode='json'), 201

    @staticmethod
    def delete(service: str, cluster_id: int):
        """
        Delete a HA cluster
        ---
        tags:
          - HA Cluster
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to delete'
            required: true
            type: 'integer'
        responses:
          204:
            description: HA cluster deletion successful
          400:
            description: Invalid request data
          404:
             description: HA cluster not found
        """
        try:
            ha_cluster.delete_cluster(cluster_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete cluster')

    @staticmethod
    def _install_service(body: HAClusterRequest, cluster_id: int):
        try:
            output = service_mod.install_service('keepalived', body, cluster_id)
        except Exception as e:
            raise e

        if len(output['failures']) > 0 or len(output['dark']) > 0:
            raise Exception('Cannot install Keepalived. Check Apache error log')

        cluster_services = ha_cluster.get_services_dict(body)
        for service, value in cluster_services.items():
            if not value['enabled']:
                continue
            else:
                try:
                    output = service_mod.install_service(service, body)
                except Exception as e:
                    raise e

                if len(output['failures']) > 0 or len(output['dark']) > 0:
                    raise Exception(f'Cannot install {service.title()}. Check Apache error log')


class HAVIPView(MethodView):
    methods = ["GET", "POST", "PUT", "DELETE"]
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def __init__(self):
        self.group_id = g.user_params['group_id']

    @staticmethod
    def get(service: str, cluster_id: int, vip_id: int):
        """
        This endpoint retrieves information about the specified VIP.
        ---
        tags:
          - HA Cluster VIP
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - name: cluster_id
            in: path
            type: integer
            required: true
            description: ID of the cluster
          - name: vip_id
            in: path
            type: integer
            required: true
            description: ID of the VIP
        responses:
          200:
            description: HAVIP details retrieved successfully
            schema:
              type: object
              properties:
                cluster_id:
                  type: integer
                  description: ID of the cluster
                eth:
                  type: string
                  description: Ethernet interface
                id:
                  type: integer
                  description: ID of the HAVIP
                return_master:
                  type: integer
                  description: Return master flag
                router_id:
                  type: integer
                  description: ID of the router
                servers:
                  type: array
                  items:
                    type: object
                    properties:
                      eth:
                        type: string
                        description: Ethernet interface
                      id:
                        type: integer
                        description: Server ID
                      master:
                        type: integer
                        description: Master flag
                use_src:
                  type: integer
                  description: Use source flag
                vip:
                  type: string
                  description: Virtual IP address
                virt_server:
                  type: integer
                  description: Virtual server flag
        """
        try:
            vip = ha_sql.select_cluster_vip_by_vip_id(cluster_id, vip_id)
            slaves = ha_sql.select_cluster_slaves(cluster_id, vip.router_id)
            settings = model_to_dict(vip, recurse=False)
            is_virt = ha_sql.check_ha_virt(vip.id)
            settings.setdefault('virt_server', is_virt)
            settings['servers'] = []
            for slave in slaves:
                server_id = slave[0]
                if slave[31]:
                    settings.setdefault('eth', slave[32])
                server_settings = {'id': server_id, 'eth': slave[32], 'master': slave[31]}
                settings['servers'].append(server_settings)
            return jsonify(settings)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get VIP')

    @validate(body=HAClusterVIP)
    def post(self, service: str, cluster_id: int, body: HAClusterVIP):
        """
        This endpoint allows to create a VIP for HA cluster.
        ---
        tags:
          - HA Cluster VIP
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to update'
            required: true
            type: 'integer'
          - in: body
            name: body
            required: true
            schema:
              required:
                - servers
                - vip
              type: object
              properties:
                servers:
                  type: 'array'
                  description: Must be at least 2 servers. One of them must be master = 1
                  items:
                    type: 'object'
                    properties:
                      id:
                        type: 'integer'
                      master:
                        type: 'integer'
                vip:
                  type: string
                virt_server:
                  type: integer
                return_master:
                  type: integer
                use_src:
                  type: integer
        responses:
          201:
            description: VIP created successfully
          400:
            description: Invalid request data
          404:
             description: VIP not found
          default:
            description: Unexpected error
        """
        try:
            vip_id = ha_cluster.insert_vip(cluster_id, body, self.group_id)
            return IdResponse(id=vip_id).model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create VIP')

    @validate(body=HAClusterVIP)
    def put(self, service: str, cluster_id: int, vip_id: int, body: HAClusterVIP):
        """
        This endpoint allows to update a VIP for HA cluster.
        ---
        tags:
          - HA Cluster VIP
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to update'
            required: true
            type: 'integer'
          - in: 'path'
            name: 'vip_id'
            description: 'ID of the VIP to update'
            required: true
            type: 'integer'
          - in: body
            name: body
            required: true
            schema:
              required:
                - servers
                - vip
              type: object
              properties:
                servers:
                  type: 'array'
                  description: Must be at least 2 servers. One of them must be master = 1
                  items:
                    type: 'object'
                    properties:
                      id:
                        type: 'integer'
                      master:
                        type: 'integer'
                vip:
                  type: string
                virt_server:
                  type: integer
                return_master:
                  type: string
                use_src:
                  type: integer
        responses:
          201:
            description: VIP updated successfully
          400:
            description: Invalid request data
          404:
             description: VIP not found
          default:
            description: Unexpected error
        """
        try:
            vip = ha_sql.select_cluster_vip_by_vip_id(cluster_id, vip_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot find VIP')
        try:
            ha_cluster.update_vip(cluster_id, vip.router_id, body, self.group_id)
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update VIP')

    @staticmethod
    def delete(service: str, cluster_id: int, vip_id: int):
        """
        Delete a VIP
        ---
        tags:
          - HA Cluster VIP
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to delete VIP from'
            required: true
            type: 'integer'
          - in: 'path'
            name: 'vip_id'
            description: 'ID of the VIP to delete'
            required: true
            type: 'integer'
        responses:
          204:
            description: VIP deletion successful
          400:
            description: Invalid request data
          404:
             description: VIP not found
        """
        vip = ha_sql.select_cluster_vip_by_vip_id(cluster_id, vip_id)
        router = ha_sql.get_router(vip.router_id)
        if router.default == 1:
            return roxywi_common.handler_exceptions_for_json_data(Exception(''), 'You cannot delete default VIP')
        try:
            ha_sql.delete_ha_router(vip.router_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete VIP')


class HAVIPsView(MethodView):
    methods = ["GET"]
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    @staticmethod
    def get(service: str, cluster_id: int):
        """
        This endpoint retrieves information about the specified VIPs.
        ---
        tags:
          - HA Cluster VIP
        parameters:
          - in: 'path'
            name: 'service'
            description: 'Can be only "cluster"'
            required: true
            type: 'string'
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to retrieve'
            required: true
            type: 'integer'
        responses:
          200:
            description: Successful operation
            schema:
              type: 'array'
              items:
                type: 'object'
                properties:
                  cluster_id:
                    type: 'object'
                    properties:
                      description:
                        type: 'string'
                      group_id:
                        type: 'integer'
                      id:
                        type: 'integer'
                      name:
                        type: 'string'
                      pos:
                        type: 'integer'
                      syn_flood:
                        type: 'integer'
                  id:
                    type: 'integer'
                  return_master:
                    type: 'integer'
                  router_id:
                    type: 'integer'
                  use_src:
                    type: 'integer'
                  vip:
                    type: 'string'
          default:
            description: Unexpected error
        """
        vips = ha_sql.select_cluster_vips(cluster_id)
        vips = [model_to_dict(vip, recurse=False) for vip in vips]
        return jsonify(vips)
