from typing import Literal

from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask import jsonify, g
from playhouse.shortcuts import model_to_dict
from flask_pydantic import validate

import app.modules.db.channel as channel_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.tools.alerting as alerting
from app.middleware import get_user_params, check_group
from app.modules.roxywi.class_models import BaseResponse, IdResponse, IdDataResponse, GroupQuery, ChannelRequest
from app.modules.common.common_classes import SupportClass


class ChannelView(MethodView):
    method_decorators = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    decorators = [jwt_required(), get_user_params(), check_group()]

    def __init__(self, is_api: bool = False):
        self.is_api = is_api

    @validate(query=GroupQuery)
    def get(self, receiver: Literal['telegram', 'slack', 'pd', 'mm'], channel_id: int, query: GroupQuery):
        """
        Get information about a channel
        ---
        tags:
          - Channel
        summary: Get Channel Information
        description: This method returns information about a specific channel, based on channel_id and receiver type.
        parameters:
        - name: receiver
          in: path
          description: The type of the receiver. Only 'telegram', 'slack', 'pd', 'mm' are allowed.
          required: true
          type: string
          enum: ['telegram', 'slack', 'pd', 'mm']
        - name: channel_id
          in: path
          description: The ID of the channel for which information should be retrieved.
          required: true
          type: integer
        produces:
          - application/json
        responses:
          200:
            description: OK
            schema:
              type: object
              properties:
                chanel_name:
                  type: string
                  description: The name of the channel.
                  example: "@tg-channel-id"
                group_id:
                  type: integer
                  description: The ID of the group to which the channel belongs. Only for superAdmin role
                  example: 1
                id:
                  type: integer
                  description: The ID of the channel.
                  example: 1
                token:
                  type: string
                  description: The token used for the channel.
                  example: "Cool channel"
        """
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            channel = channel_sql.get_receiver_with_group(receiver, channel_id, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        return model_to_dict(channel)

    @validate(body=ChannelRequest)
    def post(self, receiver: Literal['telegram', 'slack', 'pd', 'mm'], body: ChannelRequest):
        """
        Create a new channel
        ---
        tags:
          - Channel
        summary: Add Channel Information
        description: This method is used to add information for a new channel.
        parameters:
        - name: receiver
          in: path
          description: The type of the receiver. Only 'telegram', 'slack', 'pd', 'mm' are allowed.
          required: true
          type: string
          enum: ['telegram', 'slack', 'pd', 'mm']
        - in: 'body'
          name: 'body'
          description: 'Channel information to be added'
          required: true
          schema:
            type: object
            properties:
              token:
                type: string
                description: The token used for the channel.
                example: "some token"
              channel:
                type: string
                description: The channel identifier.
                example: "channel name"
              group_id:
                type: integer
                description: The ID of the group to which the channel belongs.
                example: 1
        consumes:
          - application/json
        produces:
          - application/json
        responses:
          201:
            description: Channel Created
            schema:
              type: object
              properties:
                chanel_name:
                  type: string
                  description: The name of the channel.
                  example: "@tg-channel-id"
                group_id:
                  type: integer
                  description: The ID of the group to which the channel belongs.
                  example: 1
                id:
                  type: integer
                  description: The ID of the channel.
                  example: 1
                token:
                  type: string
                  description: The token used for the channel.
                  example: "'test tg'"
        """
        roxywi_auth.page_for_admin(level=3)
        try:
            group_id = SupportClass.return_group_id(body)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            data = alerting.add_receiver(receiver, body.token, body.channel, group_id, self.is_api)
            roxywi_common.logging('Roxy-WI server', f'A new {receiver.title()} channel {body.channel} has been created ', roxywi=1,
                                  login=1)
            if self.is_api:
                return IdResponse(id=data).model_dump(mode='json'), 201
            else:
                return IdDataResponse(data=data, id=0).model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot create {body.channel} {receiver.title()} channel')

    @validate(body=ChannelRequest)
    def put(self, receiver: Literal['telegram', 'slack', 'pd', 'mm'], channel_id: int, body: ChannelRequest):
        """
        Update channel information
        ---
        tags:
          - Channel
        summary: Update Channel Information
        description: This method updates information for an existing channel given the channel_id, or creates a new one if it does not exist.
        parameters:
        - name: receiver
          in: path
          description: The type of the receiver. Only 'telegram', 'slack', 'pd', 'mm' are allowed.
          required: true
          type: string
          enum: ['telegram', 'slack', 'pd', 'mm']
        - name: channel_id
          in: path
          description: The ID of the channel for which information should be updated.
          required: true
          type: integer
        - in: 'body'
          name: 'body'
          description: 'Channel information to be updated'
          required: true
          schema:
            type: object
            properties:
              token:
                type: string
                description: The token used for the channel.
                example: "some token"
              channel:
                type: string
                description: The channel identifier.
                example: "cool channel"
              group_id:
                type: integer
                description: The ID of the group to which the channel belongs.
                example: 1
        consumes:
          - application/json
        produces:
          - application/json
        responses:
          201:
            description: Channel Created
        """
        roxywi_auth.page_for_admin(level=3)
        try:
            group_id = SupportClass.return_group_id(body)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            alerting.update_receiver_channel(receiver, body.token, body.channel, group_id, channel_id)
            roxywi_common.logging(f'group {group_id}', f'The {receiver.title()} token has been updated for channel: {body.channel}', roxywi=1, login=1)
            return BaseResponse().model_dump(mode='json'), 201
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot update {body.channel} {receiver} channel')

    @validate(query=GroupQuery)
    def patch(self, receiver: Literal['telegram', 'slack', 'pd', 'mm'], channel_id: int, query: GroupQuery):
        """
        Check a channel
        ---
        tags:
          - Channel
        summary: Send a message check to the channel.
        description: This method is used to delete a specific channel based on its ID. Optionally, the group_id can be provided by the superAdmin role to check the channel from a specific group.
        parameters:
        - name: receiver
          in: path
          description: The type of the receiver. Only 'telegram', 'slack', 'pd', 'mm' are allowed.
          required: true
          type: string
          enum: ['telegram', 'slack', 'pd', 'mm']
        - name: channel_id
          in: path
          description: The ID of the channel that needs to be deleted.
          required: true
          type: integer
        - name: group_id
          in: query
          description: The ID of the group. Optional and only for superAdmin role.
          required: false
          type: integer
        produces:
          - application/json
        responses:
          200:
            description: The message has been sent to the channel.
        """
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            _ = channel_sql.get_receiver_with_group(receiver, channel_id, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            alerting.check_receiver(channel_id, receiver)
            return BaseResponse().model_dump(mode='json'), 200
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot check {channel_id} {receiver}')

    @validate(query=GroupQuery)
    def delete(self, receiver: Literal['telegram', 'slack', 'pd', 'mm'], channel_id: int, query: GroupQuery):
        """
        Delete a channel
        ---
        tags:
          - Channel
        summary: Delete Channel Information
        description: This method is used to delete a specific channel based on its ID. Optionally, the group_id can be provided by the superAdmin role to delete the channel from a specific group.
        parameters:
        - name: receiver
          in: path
          description: The type of the receiver. Only 'telegram', 'slack', 'pd', 'mm' are allowed.
          required: true
          type: string
          enum: ['telegram', 'slack', 'pd', 'mm']
        - name: channel_id
          in: path
          description: The ID of the channel that needs to be deleted.
          required: true
          type: integer
        - name: group_id
          in: query
          description: The ID of the group. Optional and only for superAdmin role.
          required: false
          type: integer
        produces:
          - application/json
        responses:
          204:
            description: Channel Deleted
        """
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            _ = channel_sql.get_receiver_with_group(receiver, channel_id, group_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        try:
            alerting.delete_receiver_channel(channel_id, receiver)
            roxywi_common.logging('Roxy-WI server', f'The {receiver.title()} channel {channel_id} has been deleted ',
                                  roxywi=1, login=1)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, f'Cannot delete {receiver} channel')


class ChannelsView(MethodView):
    method_decorators = ["GET"]
    decorators = [jwt_required(), get_user_params(), check_group()]

    @validate()
    def get(self, receiver: Literal['telegram', 'slack', 'pd', 'mm'], query: GroupQuery):
        """
        Get information about channels
        ---
        tags:
          - Channel
        summary: Get Channels Information
        description: This method gets information about all channels, returning a list of channels in JSON format.
        parameters:
        - name: receiver
          in: path
          description: The type of the receiver. Only 'telegram', 'slack', 'pd', 'mm' are allowed.
          required: true
          type: string
          enum: ['telegram', 'slack', 'pd', 'mm']
        - in: 'query'
          name: 'group_id'
          description: 'ID of the group to list channels. For superAdmin only'
          required: false
          type: 'integer'
        produces:
          - application/json
        responses:
          200:
            description: OK
            schema:
              type: array
              items:
                type: object
                properties:
                  chanel_name:
                    type: string
                    description: The name of the channel.
                    example: "@tg-channel-id"
                  group_id:
                    type: integer
                    description: The ID of the group to which the channel belongs.
                    example: 1
                  id:
                    type: integer
                    description: The ID of the channel.
                    example: 1
                  token:
                    type: string
                    description: The token used for the channel.
                    example: "'test tg'"
        """
        try:
            group_id = SupportClass.return_group_id(query)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot get group id')

        return jsonify([model_to_dict(channel) for channel in channel_sql.get_user_receiver_by_group(receiver, group_id)])
