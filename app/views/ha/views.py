from flask.views import MethodView
from flask_pydantic import validate
from flask_jwt_extended import jwt_required
from flask import render_template, request, jsonify, g
from playhouse.shortcuts import model_to_dict

import app.modules.db.ha_cluster as ha_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.common.common as common
import app.modules.service.ha_cluster as ha_cluster
from app.middleware import get_user_params, page_for_admin, check_group, check_services
from app.modules.roxywi.class_models import (
    BaseResponse, IdResponse, HAClusterRequest, HAClusterVIP
)


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
            description: Successful operation
            schema:
              type: 'object'
              properties:
                description:
                  type: 'string'
                eth:
                  type: 'string'
                group_id:
                  type: 'integer'
                haproxy:
                  type: 'integer'
                id:
                  type: 'integer'
                name:
                  type: 'string'
                nginx:
                  type: 'integer'
                pos:
                  type: 'integer'
                syn_flood:
                  type: 'integer'
                use_src:
                  type: 'integer'
                vip:
                  type: 'string'
                virt_server:
                  type: 'boolean'
          default:
            description: Unexpected error
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

            for cluster in clusters:
                settings = model_to_dict(cluster)
            settings.setdefault('vip', vip.vip)
            settings.setdefault('virt_server', is_virt)
            settings.setdefault('use_src', vip.use_src)
            settings.setdefault('return_master', vip.return_master)

            for slave in slaves:
                if slave[31]:
                    settings.setdefault('eth', slave[32])

            for c_s in cluster_services:
                if int(c_s.service_id) == 1:
                    settings.setdefault('haproxy', 1)
                elif int(c_s.service_id) == 2:
                    settings.setdefault('nginx', 1)
                elif int(c_s.service_id) == 4:
                    settings.setdefault('apache', 1)

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
              type: object
              properties:
                servers:
                  type: 'array'
                  description: Must be at least 2 servers. One of them must be master = 1
                  items:
                    type: 'object'
                    properties:
                      ip:
                        type: 'string'
                      master:
                        type: 'integer'
                      name:
                        type: 'string'
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
                        type: string
                      docker:
                        type: integer
                router_id:
                  type: string
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
            return IdResponse(id=cluster_id).model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create cluster')

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
              type: object
              properties:
                servers:
                  type: 'array'
                  description: Must be at least 2 servers. One of them must be master = 1
                  items:
                    type: 'object'
                    properties:
                      ip:
                        type: 'string'
                      master:
                        type: 'integer'
                      name:
                        type: 'string'
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
                        type: string
                      docker:
                        type: integer
                router_id:
                  type: string
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
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update cluster')

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


class HAVIPView(MethodView):
    methods = ["GET", "POST", "PUT", "DELETE"]
    decorators = [jwt_required(), get_user_params(), check_services, page_for_admin(level=3), check_group()]

    def __init__(self):
        self.group_id = g.user_params['group_id']

    @staticmethod
    def get(service: str, cluster_id: int, router_id: int):
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
          - in: 'path'
            name: 'cluster_id'
            description: 'ID of the HA cluster to retrieve'
            required: true
            type: 'integer'
          - in: 'path'
            name: 'router_id'
            description: 'ID of the Router to retrieve'
            required: true
            type: 'integer'
        responses:
          200:
            description: Successful operation
            schema:
              type: object
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
                  type: 'object'
                  properties:
                    id:
                      type: 'integer'
                use_src:
                  type: 'integer'
                vip:
                  type: 'string'
          default:
            description: Unexpected error
        """
        try:
            vip = ha_sql.select_cluster_vip(cluster_id, router_id)
            settings = model_to_dict(vip)
            is_virt = ha_sql.check_ha_virt(vip.id)
            settings.setdefault('virt_server', is_virt)
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
              type: object
              properties:
                servers:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      eth:
                        type: string
                      ip:
                        type: string
                      name:
                        type: string
                      master:
                        type: integer
                name:
                  type: string
                description:
                  type: string
                vip:
                  type: string
                virt_server:
                  type: integer
                return_master:
                  type: string
                syn_flood:
                  type: integer
                use_src:
                  type: integer
                router_id:
                  type: string
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
            ha_cluster.insert_vip(cluster_id, body, self.group_id)
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create VIP')


    @validate(body=HAClusterVIP)
    def put(self, service: str, cluster_id: int, body: HAClusterVIP):
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
          - in: body
            name: body
            required: true
            schema:
              type: object
              properties:
                servers:
                  type: object
                  additionalProperties:
                    type: object
                    properties:
                      eth:
                        type: string
                      ip:
                        type: string
                      name:
                        type: string
                      master:
                        type: integer
                name:
                  type: string
                description:
                  type: string
                vip:
                  type: string
                virt_server:
                  type: integer
                return_master:
                  type: string
                syn_flood:
                  type: integer
                use_src:
                  type: integer
                router_id:
                  type: string
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
            ha_cluster.update_vip(cluster_id, body.router_id, body, self.group_id)
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update VIP')

    @staticmethod
    def delete(service: str, router_id: int):
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
            name: 'router_id'
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
        router = ha_sql.get_router(router_id)
        if router.default == 1:
            return roxywi_common.handler_exceptions_for_json_data(Exception(''), 'You cannot delete default VIP')
        try:
            ha_sql.delete_ha_router(router_id)
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
                    type: 'object'
                    properties:
                      id:
                        type: 'integer'
                  use_src:
                    type: 'integer'
                  vip:
                    type: 'string'
          default:
            description: Unexpected error
        """
        vips = ha_sql.select_cluster_vips(cluster_id)
        vips = [model_to_dict(vip) for vip in vips]
        return jsonify(vips)
