from pydantic import ValidationError
from peewee import IntegrityError
from flask import jsonify, request

from app.routes.admin import bp
from app.modules.db import oidc as oidc_sql
from app.modules.oidc.access import oidc_subscription_required
from app.modules.oidc.schemas import OidcGroupMappingRequest, OidcProviderCreate, OidcProviderUpdate
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiValidationError
from app.routes.oidc.routes import _public_oidc_url


def _validation_error(exc: ValidationError):
    errors = [
        {
            'field': '.'.join(str(part) for part in error['loc']),
            'message': error['msg'],
        }
        for error in exc.errors()
    ]
    return jsonify({'status': 'failed', 'error': 'validation_error', 'details': errors}), 400


def _serialize_provider(provider):
    data = oidc_sql.serialize_provider(provider)
    data['callback_url'] = _public_oidc_url(provider.slug)
    return data


def _validate_enabled_provider(data: dict, existing=None) -> None:
    def value(name):
        if name in data:
            return data[name]
        return getattr(existing, name, None) if existing else None

    if not value('enabled'):
        return
    if not value('client_id'):
        raise RoxywiValidationError('An enabled OIDC provider requires client_id')
    if value('metadata_url'):
        return
    required = ('issuer', 'authorization_endpoint', 'token_endpoint', 'jwks_uri')
    missing = [field for field in required if not value(field)]
    if missing:
        raise RoxywiValidationError(
            'An enabled OIDC provider requires metadata_url or these fields: ' + ', '.join(missing)
        )


@bp.get('/oidc/providers')
@oidc_subscription_required
def list_oidc_providers():
    roxywi_auth.page_for_admin()
    return jsonify([_serialize_provider(provider) for provider in oidc_sql.list_providers()])


@bp.post('/oidc/providers')
@oidc_subscription_required
def create_oidc_provider():
    roxywi_auth.page_for_admin()
    try:
        body = OidcProviderCreate.model_validate(request.get_json(silent=True) or {})
        data = body.model_dump()
        _validate_enabled_provider(data)
        provider = oidc_sql.create_provider(data)
    except ValidationError as exc:
        return _validation_error(exc)
    except RoxywiValidationError as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 400
    except IntegrityError:
        return jsonify({'status': 'failed', 'error': 'An OIDC provider with this slug already exists'}), 409

    roxywi_common.logging('Roxy-WI server', f'OIDC provider {provider.slug} has been created', roxywi=1, login=1)
    return jsonify(_serialize_provider(provider)), 201


@bp.put('/oidc/providers/<int:provider_id>')
@oidc_subscription_required
def update_oidc_provider(provider_id: int):
    roxywi_auth.page_for_admin()
    try:
        provider = oidc_sql.get_provider(provider_id)
        body = OidcProviderUpdate.model_validate(request.get_json(silent=True) or {})
        data = body.model_dump(exclude_unset=True)
        # An empty secret means "keep the existing secret".
        if data.get('client_secret') == '':
            data.pop('client_secret')
        _validate_enabled_provider(data, existing=provider)
        provider = oidc_sql.update_provider(provider_id, data)
    except ValidationError as exc:
        return _validation_error(exc)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 404
    except RoxywiValidationError as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 400
    except IntegrityError:
        return jsonify({'status': 'failed', 'error': 'An OIDC provider with this slug already exists'}), 409

    roxywi_common.logging('Roxy-WI server', f'OIDC provider {provider.slug} has been updated', roxywi=1, login=1)
    return jsonify(_serialize_provider(provider))


@bp.get('/oidc/providers/<int:provider_id>/mappings')
@oidc_subscription_required
def list_oidc_mappings(provider_id: int):
    roxywi_auth.page_for_admin()
    try:
        oidc_sql.get_provider(provider_id)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 404
    return jsonify([oidc_sql.serialize_mapping(mapping) for mapping in oidc_sql.list_mappings(provider_id)])


@bp.post('/oidc/providers/<int:provider_id>/mappings')
@oidc_subscription_required
def create_oidc_mapping(provider_id: int):
    roxywi_auth.page_for_admin()
    try:
        body = OidcGroupMappingRequest.model_validate(request.get_json(silent=True) or {})
        mapping = oidc_sql.create_mapping(provider_id, body.model_dump())
    except ValidationError as exc:
        return _validation_error(exc)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 404
    except RoxywiValidationError as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 400
    except IntegrityError:
        return jsonify({'status': 'failed', 'error': 'This OIDC group mapping already exists'}), 409

    return jsonify(oidc_sql.serialize_mapping(mapping)), 201


@bp.put('/oidc/mappings/<int:mapping_id>')
@oidc_subscription_required
def update_oidc_mapping(mapping_id: int):
    roxywi_auth.page_for_admin()
    try:
        body = OidcGroupMappingRequest.model_validate(request.get_json(silent=True) or {})
        mapping = oidc_sql.update_mapping(mapping_id, body.model_dump())
    except ValidationError as exc:
        return _validation_error(exc)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 404
    except RoxywiValidationError as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 400
    except IntegrityError:
        return jsonify({'status': 'failed', 'error': 'This OIDC group mapping already exists'}), 409
    return jsonify(oidc_sql.serialize_mapping(mapping))


@bp.delete('/oidc/mappings/<int:mapping_id>')
@oidc_subscription_required
def delete_oidc_mapping(mapping_id: int):
    roxywi_auth.page_for_admin()
    try:
        oidc_sql.delete_mapping(mapping_id)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 404
    return jsonify({'status': 'Ok'})
