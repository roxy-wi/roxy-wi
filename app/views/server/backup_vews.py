from flask.views import MethodView
from flask_pydantic import validate
from flask import jsonify
from playhouse.shortcuts import model_to_dict
from flask_jwt_extended import jwt_required

import app.modules.db.backup as backup_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.service.backup as backup_mod
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params, page_for_admin, check_group
from app.modules.roxywi.class_models import BackupRequest, S3BackupRequest, GitBackupRequest, BaseResponse


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
            backup.server_id = int(backup.server_id)
            backup.description = str(backup.description).replace("'", "")
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
              required:
                - cred_id
                - rhost
                - rpath
                - server_id
                - rserver
                - time
                - type
              properties:
                server_id:
                    type: 'string'
                    description: 'The server ID to be backed up'
                rserver:
                    type: 'string'
                    description: 'The remote server where backup files should be stored'
                    example: 10.0.0.1
                rpath:
                    type: 'string'
                    description: 'The path on the remote server where backup files should be stored'
                    example: /var/backup/
                type:
                    type: 'string'
                    description: 'Type of the operation'
                    enum: [backup, synchronization]
                time:
                    type: 'string'
                    description: 'The timing for the backup task'
                    enum: [hourly, daily, weekly, monthly]
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
              required:
                - cred_id
                - rhost
                - rpath
                - server_id
                - rserver
                - time
                - type
              properties:
                server_id:
                    type: 'integer'
                    description: 'The server ID to be backed up'
                rserver:
                    type: 'string'
                    description: 'The remote server where backup files should be stored'
                    example: 10.0.0.1
                rpath:
                    type: 'string'
                    description: 'The path on the remote server where backup files should be stored'
                    example: /var/backup/
                type:
                    type: 'string'
                    description: 'Type of the operation'
                    enum: [backup, synchronization]
                time:
                    type: 'string'
                    description: 'The timing for the backup task'
                    enum: [hourly, daily, weekly, monthly]
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
                server_id:
                    type: 'integer'
                    description: 'The server ID to be backed up'
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
    methods = ['GET', 'POST', 'DELETE']
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
                server_id:
                    type: 'integer'
                    description: 'The server ID that was backed up'
                time:
                    type: 'string'
                    description: 'The timing for the S3 backup task'
          default:
            description: Unexpected error
        """
        try:
            backup = backup_sql.get_backup(backup_id, 's3')
            backup.server_id = int(backup.server_id)
            backup.description = str(backup.description).replace("'", "")
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
              required:
                - s3_server
                - server_id
                - bucket
                - secret_key
                - access_key
                - time
              properties:
                s3_server:
                    type: 'string'
                    description: 'The S3 server where the backup should be stored'
                server_id:
                    type: 'integer'
                    description: 'The server ID to be backed up'
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
                    enum: [hourly, daily, weekly, monthly]
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
    def put(self, backup_id: int, body: S3BackupRequest):
        """
        Update the S3 backup.
        ---
        tags:
          - S3 Backup
        parameters:
          - in: path
            name: backup_id
            type: 'integer'
            required: true
            description: The ID of the specific S3 backup
          - name: config
            in: body
            required: true
            description: The configuration for S3 backup service
            schema:
              type: 'object'
              required:
                - s3_server
                - server_id
                - bucket
                - secret_key
                - access_key
                - time
              properties:
                s3_server:
                    type: 'string'
                    description: 'The S3 server where the backup should be stored'
                server_id:
                    type: 'integer'
                    description: 'The server ID to be backed up'
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
                    enum: [hourly, daily, weekly, monthly]
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
            backup_mod.create_s3_backup_inv(body, 'add')
            backup_sql.update_backup_job(backup_id, 's3', **body.model_dump(mode='json'))
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update S3 backup')

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
                server_id:
                    type: 'integer'
                    description: 'The server ID that was backed up'
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


class GitBackupView(MethodView):
    methods = ['GET', 'POST', 'DELETE']
    decorators = [jwt_required(), get_user_params(), page_for_admin(), check_group()]

    def __init__(self, is_api=True):
        self.is_api = is_api

    @staticmethod
    def get(backup_id: int):
        """
        Retrieves the details of a specific Git backup configuration.
        ---
        tags:
          - Git Backup
        parameters:
          - in: path
            name: backup_id
            type: 'integer'
            required: true
            description: The ID of the specific Git backup
        responses:
          200:
            description: Successful operation
            schema:
              type: 'object'
              properties:
                branch:
                    type: 'string'
                    description: 'The branch the backup is on'
                cred_id:
                    type: 'integer'
                    description: 'The ID of the credentials used for the backup'
                description:
                    type: 'string'
                    description: 'Description for the Git backup configuration'
                id:
                    type: 'integer'
                    description: 'The ID of the backup'
                period:
                    type: 'string'
                    description: 'The timing for the Git backup task'
                repo:
                    type: 'string'
                    description: 'The repository URL for the backup'
                server_id:
                    type: 'integer'
                    description: 'The ID of the server that was backed up'
                service_id:
                    type: 'integer'
                    description: 'The service ID of the backup'
          default:
            description: Unexpected error
        """
        try:
            backup = backup_sql.get_backup(backup_id, 'git')
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, '')

        return jsonify(model_to_dict(backup, recurse=False))

    @validate(body=GitBackupRequest)
    def post(self, body: GitBackupRequest):
        """
        Create a new Git backup.
        ---
        tags:
          - Git Backup
        parameters:
          - name: config
            in: body
            required: true
            description: The configuration for Git backup service
            schema:
              type: 'object'
              required:
                - cred_id
                - server_id
                - service_id
                - init
                - repo
                - branch
                - time
              properties:
                server_id:
                    type: 'integer'
                    description: 'The ID of the server to backed up'
                service_id:
                    type: 'integer'
                    description: 'Service ID: 1: HAProxy, 2: NGINX, 3: Keepalived, 4: Apache'
                    example: 1
                init:
                    type: 'integer'
                    description: 'Indicates whether to initialize the repository'
                repo:
                    type: 'string'
                    description: 'The repository from where to fetch the data for backup'
                    example: git@github.com:Example/haproxy_configs
                branch:
                    type: 'string'
                    description: 'The branch to pull for backup'
                    example: 'master'
                time:
                    type: 'string'
                    description: 'The timing for the Git backup task'
                    enum: [hourly, daily, weekly, monthly]
                cred_id:
                    type: 'integer'
                    description: 'The ID of the credentials to be used for backup'
                description:
                    type: 'string'
                    description: 'Description for the Git backup configuration'
        responses:
          201:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            return backup_mod.create_git_backup(body, self.is_api)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create GIT backup')

    @validate(body=GitBackupRequest)
    def put(self, backup_id: int, body: GitBackupRequest):
        """
        Update a new Git backup.
        ---
        tags:
          - Git Backup
        parameters:
          - name: config
            in: body
            required: true
            description: The configuration for Git backup service
            schema:
              type: 'object'
              required:
                - cred_id
                - server_id
                - service_id
                - init
                - repo
                - branch
                - time
              properties:
                server_id:
                    type: 'integer'
                    description: 'The ID of the server to backed up'
                service_id:
                    type: 'integer'
                    description: 'Service ID: 1: HAProxy, 2: NGINX, 3: Keepalived, 4: Apache'
                    example: 1
                init:
                    type: 'integer'
                    description: 'Indicates whether to initialize the repository'
                repo:
                    type: 'string'
                    description: 'The repository from where to fetch the data for backup'
                    example: git@github.com:Example/haproxy_configs
                branch:
                    type: 'string'
                    description: 'The branch to pull for backup'
                    example: 'master'
                time:
                    type: 'string'
                    description: 'The timing for the Git backup task'
                    enum: [hourly, daily, weekly, monthly]
                cred_id:
                    type: 'integer'
                    description: 'The ID of the credentials to be used for backup'
                description:
                    type: 'string'
                    description: 'Description for the Git backup configuration'
        responses:
          201:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            server = server_sql.get_server(body.server_id)
            service_name = service_sql.select_service_name_by_id(body.service_id).lower()
            backup_mod.create_git_backup_inv(body, server.ip, service_name)
            backup_sql.update_backup_job(backup_id, 'git', **body.model_dump(mode='json', exclude={'init'}))
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update GIT backup')
        return BaseResponse().model_dump(mode='json'), 201

    @validate(body=GitBackupRequest)
    def delete(self, backup_id: int, body: GitBackupRequest):
        """
        Deletes a specific Git based backup configuration.
        ---
        tags:
          - Git Backup
        parameters:
          - in: path
            name: backup_id
            type: 'integer'
            required: true
            description: The ID of the specific Git backup
          - name: config
            in: body
            required: true
            description: The configuration for Git backup service delete operation
            schema:
              type: 'object'
              properties:
                server_id:
                    type: 'integer'
                    description: 'ID of the server from where the backup is to be deleted'
                service_id:
                    type: 'integer'
                    description: 'Service ID of the backup to be deleted'
        responses:
          204:
            description: Successful operation
          default:
            description: Unexpected error
        """
        try:
            return backup_mod.delete_git_backup(body, backup_id)
        except Exception as e:
            return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete GIT backup')
