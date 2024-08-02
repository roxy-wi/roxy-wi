from flask.views import MethodView
from flask_pydantic import validate
from flask import jsonify
from playhouse.shortcuts import model_to_dict
from flask_jwt_extended import jwt_required

import app.modules.db.backup as backup_sql
import app.modules.service.backup as backup_mod
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.class_models import BackupRequest, S3BackupRequest, BaseResponse


class BackupView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), page_for_admin(), check_group()]

    def __init__(self, is_api=True):
        self.is_api = is_api

    @staticmethod
    def get(backup_id: int):
        """
        Retrieves the details of a specific backup configuration.
        ---
        tags:
          - File system backup
        parameters:
          - in: path
            name: backup_id
            type: integer
            required: true
            description: The ID of the specific backup
        responses:
          200:
            description: Successful operation
            schema:
              type: 'object'
              properties:
                cred_id:
                    type: 'integer'
                    description: 'Credentials ID for the backup task'
                description:
                    type: 'string'
                    description: 'Description for the backup configuration'
                id:
                    type: 'integer'
                    description: 'Unique identifier of the backup configuration'
                rhost:
                    type: 'string'
                    description: 'The remote server where backup files should be stored'
                rpath:
                    type: 'string'
                    description: 'The path on the remote server where backup files should be stored'
                server:
                    type: 'string'
                    description: 'The server to be backed up'
                time:
                    type: 'string'
                    description: 'The timing for the backup task'
                type:
                    type: 'string'
                    description: 'Type of the operation'
          default:
            description: Unexpected error
        """
        try:
            backup = backup_sql.get_backup(backup_id, 'fs')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        return jsonify(model_to_dict(backup))

    @validate(body=BackupRequest)
    def post(self, body: BackupRequest):
        """
        Create a new file system backup for services.
        ---
        tags:
          - File system backup
        parameters:
          - name: config
            in: body
            required: true
            description: The configuration for backup service
            schema:
              type: 'object'
              properties:
                server:
                    type: 'string'
                    description: 'The server to be backed up'
                rserver:
                    type: 'string'
                    description: 'The remote server where backup files should be stored'
                rpath:
                    type: 'string'
                    description: 'The path on the remote server where backup files should be stored'
                type:
                    type: 'string'
                    description: 'Type of the operation'
                time:
                    type: 'string'
                    description: 'The timing for the backup task'
                cred_id:
                    type: 'string'
                    description: 'Credentials ID for the backup task'
                description:
                    type: 'string'
                    description: 'Description for the backup configuration'
        responses:
          201:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            return backup_mod.create_backup(body, self.is_api)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

    @validate(body=BackupRequest)
    def put(self, backup_id: int, body: BackupRequest):
        """
        Update the file system backup for services.
        ---
        tags:
          - File system backup
        parameters:
          - in: 'path'
            name: 'backup_id'
            description: 'ID of the backup to be updated'
            required: true
            type: 'integer'
          - name: config
            in: body
            required: true
            description: The configuration for backup service
            schema:
              type: 'object'
              properties:
                server:
                    type: 'string'
                    description: 'The server to be backed up'
                rserver:
                    type: 'string'
                    description: 'The remote server where backup files should be stored'
                rpath:
                    type: 'string'
                    description: 'The path on the remote server where backup files should be stored'
                type:
                    type: 'string'
                    description: 'Type of the operation'
                time:
                    type: 'string'
                    description: 'The timing for the backup task'
                cred_id:
                    type: 'string'
                    description: 'Credentials ID for the backup task'
                description:
                    type: 'string'
                    description: 'Description for the backup configuration'
        responses:
          201:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            return backup_mod.update_backup(body, backup_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

    @validate(body=BackupRequest)
    def delete(self, backup_id: int, body: BackupRequest):
        """
        Delete the file system backup for services.
        ---
        tags:
          - File system backup
        parameters:
          - in: 'path'
            name: 'backup_id'
            description: 'ID of the backup to be deleted'
            required: true
            type: 'integer'
          - name: config
            in: body
            required: true
            description: The configuration for backup service
            schema:
              type: 'object'
              properties:
                server:
                    type: 'string'
                    description: 'The server to be backed up'
                cred_id:
                    type: 'string'
                    description: 'Credentials ID for the backup task'
        responses:
          204:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            return backup_mod.delete_backup(body, backup_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')


class S3BackupView(MethodView):
    methods = ['GET', 'POST', 'PUT', 'DELETE']
    decorators = [jwt_required(), get_user_params(), page_for_admin(), check_group()]

    def __init__(self, is_api=True):
        self.is_api = is_api

    @staticmethod
    def get(backup_id: int):
        """
        Retrieves the details of a specific S3 backup configuration.
        ---
        tags:
          - S3 Backup
        parameters:
          - in: path
            name: backup_id
            type: 'integer'
            required: true
            description: The ID of the specific S3 backup
        responses:
          200:
            description: Successful operation
            schema:
              type: 'object'
              properties:
                access_key:
                    type: 'string'
                    description: 'The access key for S3'
                bucket:
                    type: 'string'
                    description: 'The S3 bucket where the backup is stored'
                description:
                    type: 'string'
                    description: 'Description for the S3 backup configuration'
                id:
                    type: 'integer'
                    description: 'Unique identifier of the S3 backup configuration'
                s3_server:
                    type: 'string'
                    description: 'The S3 server where the backup is stored'
                secret_key:
                    type: 'string'
                    description: 'The secret key for S3 access'
                server:
                    type: 'string'
                    description: 'The server that was backed up'
                time:
                    type: 'string'
                    description: 'The timing for the S3 backup task'
          default:
            description: Unexpected error
        """
        try:
            backup = backup_sql.get_backup(backup_id, 's3')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        return jsonify(model_to_dict(backup))

    @validate(body=S3BackupRequest)
    def post(self, body: S3BackupRequest):
        """
        Create a new S3 backup.
        ---
        tags:
          - S3 Backup
        parameters:
          - name: config
            in: body
            required: true
            description: The configuration for S3 backup service
            schema:
              type: 'object'
              properties:
                s3_server:
                    type: 'string'
                    description: 'The S3 server where the backup should be stored'
                server:
                    type: 'string'
                    description: 'The server to be backed up'
                bucket:
                    type: 'string'
                    description: 'The S3 bucket where the backup should be stored'
                secret_key:
                    type: 'string'
                    description: 'The secret key for S3 access'
                access_key:
                    type: 'string'
                    description: 'The access key for S3'
                time:
                    type: 'string'
                    description: 'The timing for the S3 backup task'
                description:
                    type: 'string'
                    description: 'Description for the S3 backup configuration'
        responses:
          201:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            return backup_mod.create_s3_backup(body, self.is_api)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create S3 backup')

    @validate(body=S3BackupRequest)
    def delete(self, backup_id: int, body: S3BackupRequest):
        """
        Deletes a specific S3 based backup configuration.
        ---
        tags:
          - S3 Backup
        parameters:
          - in: path
            name: backup_id
            type: 'integer'
            required: true
            description: The ID of the specific S3 backup
          - in: body
            name: s3_details
            required: true
            description: The details of the S3 backup to be deleted
            schema:
              type: 'object'
              properties:
                bucket:
                    type: 'string'
                    description: 'The S3 bucket where the backup is stored'
                server:
                    type: 'string'
                    description: 'The server that was backed up'
        responses:
          200:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            backup_mod.delete_s3_backup(body, backup_id)
            return BaseResponse().model_dump(mode='json'), 204
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete S3 backup')
