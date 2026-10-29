"""SSL page endpoints sharing the certificate deployment used by Let's Encrypt."""
from typing import Literal, Optional
from uuid import UUID

from flask import g
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from pydantic import BaseModel, Field

from app.middleware import get_user_params
from app.modules.config.path_tokens import decode_file_path
from app.modules.roxywi import common
from app.modules.roxywi import logger
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiInputError
from app.modules.service import certificates, certificate_operations as operations


class CertificatePreview(BaseModel):
    pem: str = Field(min_length=1, max_length=certificates.MAX_PEM_BYTES)


class CertificateUpload(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    cert: str = Field(min_length=1, max_length=certificates.MAX_PEM_BYTES)
    cert_type: Literal['key', 'crt', 'pem'] = 'pem'


class CertificateUpdate(CertificatePreview):
    name: str = Field(min_length=1, max_length=255)
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    operation_id: UUID
    directory: Optional[str] = Field(default=None, min_length=1, max_length=4096)


class CertificateDestination(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    kind: Literal['crt_list', 'directory']


class CertificateDelete(BaseModel):
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')


class CertificateHistoryQuery(BaseModel):
    page: int = Field(default=1, ge=1, le=2147483647)
    per_page: int = Field(default=10, ge=1, le=50)


class CertificateCreate(CertificatePreview):
    name: str = Field(min_length=5, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*\.pem$')
    destination: CertificateDestination
    operation_id: UUID


def identity():
    return int(g.user_params['group_id']), common.get_jwt_token_claims()['user_id']


def failure(error):
    if isinstance(error, RoxywiInputError):
        return {'status': 'failed', 'error_code': 'invalid_path'}, 400
    if isinstance(error, RoxywiResourceNotFound):
        return {'status': 'failed', 'error_code': 'not_found'}, 404
    if isinstance(error, certificates.CertificateError):
        code = error.code
        status = 403 if code in ('permission_denied', 'direct_disabled') else 409 if code in (
            'concurrent_change', 'transaction_busy') else 400
        return {'status': 'failed', 'error_code': code}, status
    logger.error('Certificate request failed', error_type=type(error).__name__)
    return {'status': 'failed', 'error_code': 'operation_failed'}, 500


class CertificatesView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    def get(self, server_id, service='haproxy'):
        try:
            group_id, user_id = identity()
            server = operations.authorize(server_id, group_id, user_id, service=service)
            result = certificates.catalog(server, service=service)
            writable = True
            try:
                operations.authorize(server_id, group_id, user_id, write=True, service=service)
            except certificates.CertificateError:
                writable = False
                result['can_create'] = False
                for item in result['certificates']:
                    item['can_update'] = False
                    item['update_error'] = 'permission_denied'
            for item in result['certificates']:
                item['can_delete'] = writable and item['can_delete']
                if not writable:
                    item['delete_error'] = 'permission_denied'
                    if item['name'].lower().endswith('.key'):
                        item['can_view'] = False
            result['operations'] = []
            if service != 'haproxy':
                return result
            result['operations'] = [operations.public_task(task) for task in
                                    operations.server_tasks(server_id, group_id).limit(50)]
            return result
        except Exception as error:
            return failure(error)

    @validate(body=CertificateUpdate)
    def post(self, server_id: int, body: CertificateUpdate):
        try:
            group_id, user_id = identity()
            return operations.enqueue(server_id, group_id, user_id, body.name, body.pem,
                                      body.revision, body.operation_id, directory=body.directory), 202
        except Exception as error:
            return failure(error)


class CertificateFileView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    def get(self, service, server_id, file_token):
        try:
            path = decode_file_path(file_token)
            group_id, user_id = identity()
            server = operations.authorize(server_id, group_id, user_id, write=path.lower().endswith('.key'), service=service)
            return certificates.certificate_file(server, service, path), 200, {'Cache-Control': 'no-store'}
        except Exception as error:
            return failure(error)

    @validate(body=CertificateDelete)
    def delete(self, service: str, server_id: int, file_token: str, body: CertificateDelete):
        try:
            path = decode_file_path(file_token)
            group_id, user_id = identity()
            server = operations.authorize(server_id, group_id, user_id, write=True, service=service)
            return certificates.certificate_file(server, service, path, revision=body.revision)
        except Exception as error:
            return failure(error)


class CertificateUploadView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    @validate(body=CertificateUpload)
    def post(self, service: str, server_id: int, body: CertificateUpload):
        try:
            group_id, user_id = identity()
            targets = certificates.targets_for(server_id, group_id)
            # Authorize all members before writing the first file.
            for server in targets:
                operations.authorize(server.server_id, group_id, user_id, write=True, service=service)
            for server in targets:
                certificates.store_uploaded_file(server.ip, body.name + '.' + body.cert_type, body.cert, service=service)
            return {'status': 'completed'}, 201
        except Exception as error:
            return failure(error)


class CertificateCreateView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    @validate(body=CertificateCreate)
    def post(self, server_id: int, body: CertificateCreate):
        try:
            group_id, user_id = identity()
            return operations.enqueue(server_id, group_id, user_id, body.name, body.pem, '', body.operation_id,
                                      destination=body.destination.model_dump()), 202
        except Exception as error:
            return failure(error)


class CertificatePreviewView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    @validate(body=CertificatePreview)
    def post(self, server_id: int, body: CertificatePreview):
        try:
            group_id, user_id = identity()
            operations.authorize(server_id, group_id, user_id, write=True)
            _bundle, metadata = certificates.inspect_pem(body.pem)
            return metadata
        except Exception as error:
            return failure(error)


class CertificateHistoryView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    @validate(query=CertificateHistoryQuery)
    def get(self, server_id: int, query: CertificateHistoryQuery):
        try:
            group_id, user_id = identity()
            operations.authorize(server_id, group_id, user_id)
            return operations.history(server_id, group_id, query.page, query.per_page)
        except Exception as error:
            return failure(error)


class CertificateOperationView(MethodView):
    decorators = [jwt_required(), get_user_params()]

    def get(self, task_id):
        try:
            group_id, user_id = identity()
            task = operations.owned_task(task_id, group_id)
            for server_id in task.server_ids:
                operations.authorize(server_id, group_id, user_id)
            return operations.public_task(task)
        except Exception as error:
            return failure(error)

    def post(self, task_id):
        try:
            group_id, user_id = identity()
            return operations.retry(operations.owned_task(task_id, group_id), user_id), 202
        except Exception as error:
            return failure(error)
