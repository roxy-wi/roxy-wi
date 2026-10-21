import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError as AuthlibJoseError
from authlib.oidc.core import CodeIDToken
from joserfc.errors import JoseError as JoseRFCError
from flask import current_app, jsonify, redirect, request, session, url_for

from app.modules.db import oidc as oidc_sql
from app.modules.oidc.access import oidc_subscription_required
from app.modules.oidc.errors import OidcLoginError
from app.modules.oidc.login import complete_oidc_login
import app.modules.roxywi.auth as roxywi_auth
from app.modules.roxywi import logger
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.server.ssh import decrypt_password
from app.routes.oidc import bp


def _public_oidc_url(slug: str) -> str:
    public_url = current_app.config.get('PUBLIC_URL', '').rstrip('/')
    if public_url:
        return f'{public_url}/oidc/{slug}/callback'
    return url_for('oidc.oidc_callback', slug=slug, _external=True)


def _safe_provider(provider) -> dict:
    return {
        'slug': provider.slug,
        'label': provider.label,
    }


def _load_json_url(url: str, error_code: str, error_message: str) -> dict:
    try:
        req = UrlRequest(url, headers={'Accept': 'application/json'})
        with urlopen(req, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError('OIDC JSON response is too large')
            document = json.loads(body.decode('utf-8'))
            if not isinstance(document, dict):
                raise ValueError('OIDC JSON response must be an object')
            return document
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise OidcLoginError(error_code, error_message, 502) from exc


def _load_metadata(provider) -> dict:
    if not provider.metadata_url:
        return {}
    return _load_json_url(
        provider.metadata_url,
        'oidc_metadata_error',
        'Could not load OIDC metadata',
    )


def _endpoint(provider, metadata: dict, field_name: str, metadata_name: str):
    return getattr(provider, field_name) or metadata.get(metadata_name)


def _load_jwks(provider, metadata: dict) -> dict:
    jwks_uri = provider.jwks_uri or metadata.get('jwks_uri')
    if not jwks_uri:
        raise OidcLoginError('oidc_jwks_missing', 'OIDC JWKS URI is not configured', 400)
    return _load_json_url(jwks_uri, 'oidc_jwks_error', 'Could not load OIDC JWKS')


def _allowed_algorithms(metadata: dict) -> list[str]:
    algorithms = metadata.get('id_token_signing_alg_values_supported') or ['RS256']
    return [algorithm for algorithm in algorithms if algorithm and algorithm.lower() != 'none']


def _validate_id_token(provider, metadata: dict, token: dict, expected_nonce: str) -> dict:
    id_token = token.get('id_token')
    if not id_token:
        raise OidcLoginError(
            'oidc_id_token_missing',
            'OIDC token response did not contain id_token',
            400,
        )

    issuer = provider.issuer or metadata.get('issuer')
    if not issuer:
        raise OidcLoginError('oidc_issuer_missing', 'OIDC issuer is not configured', 400)
    if not provider.client_id:
        raise OidcLoginError('oidc_client_id_missing', 'OIDC client_id is not configured', 400)
    if not expected_nonce:
        raise OidcLoginError('oidc_nonce_missing', 'OIDC nonce is missing or expired', 400)

    algorithms = _allowed_algorithms(metadata)
    if not algorithms:
        raise OidcLoginError(
            'oidc_alg_missing',
            'OIDC provider did not expose supported signing algorithms',
            400,
        )

    key_set = JsonWebKey.import_key_set(_load_jwks(provider, metadata))
    decoder = JsonWebToken(algorithms)
    claims_options = {
        'iss': {'essential': True, 'values': [issuer]},
        'sub': {'essential': True},
        'exp': {'essential': True},
        'iat': {'essential': True},
    }
    claims_params = {
        'client_id': provider.client_id,
        'nonce': expected_nonce,
        'access_token': token.get('access_token'),
    }

    try:
        claims = decoder.decode(
            id_token,
            key=key_set,
            claims_cls=CodeIDToken,
            claims_options=claims_options,
            claims_params=claims_params,
        )
        claims.validate(leeway=120)
    except (AuthlibJoseError, JoseRFCError, ValueError) as exc:
        raise OidcLoginError(
            'oidc_id_token_invalid',
            'OIDC id_token validation failed',
            401,
        ) from exc

    return dict(claims)


def _client_secret(provider):
    if not provider.client_secret_encrypted:
        return None
    return decrypt_password(provider.client_secret_encrypted)


def _fetch_userinfo(provider, metadata: dict, token: dict) -> dict:
    endpoint = _endpoint(provider, metadata, 'userinfo_endpoint', 'userinfo_endpoint')
    if not endpoint:
        return {}
    try:
        oauth = OAuth2Session(
            client_id=provider.client_id,
            client_secret=_client_secret(provider),
            token=token,
        )
        response = oauth.get(endpoint, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise OidcLoginError(
            'oidc_userinfo_failed',
            'Could not fetch OIDC userinfo',
            502,
        ) from exc


def _merge_claims(id_token_claims: dict, userinfo_claims: dict) -> dict:
    claims = dict(userinfo_claims or {})
    userinfo_subject = claims.get('sub')
    token_subject = id_token_claims.get('sub')
    if userinfo_subject and token_subject and str(userinfo_subject) != str(token_subject):
        raise OidcLoginError(
            'oidc_subject_mismatch',
            'OIDC userinfo subject does not match id_token subject',
            401,
        )
    # Security-sensitive claims from the verified ID token take precedence.
    claims.update(id_token_claims)
    return claims


def _error_response(error: OidcLoginError):
    return jsonify({'status': 'failed', 'error': error.error, 'message': error.message}), error.status_code


@bp.get('/providers')
@oidc_subscription_required
def public_providers():
    return jsonify([_safe_provider(provider) for provider in oidc_sql.list_providers(enabled_only=True)])


@bp.get('/<slug>/login')
@oidc_subscription_required
def oidc_login(slug: str):
    try:
        provider = oidc_sql.get_provider_by_slug(slug, enabled_only=True)
        metadata = _load_metadata(provider)
        authorization_endpoint = _endpoint(
            provider, metadata, 'authorization_endpoint', 'authorization_endpoint'
        )
        if not authorization_endpoint:
            raise OidcLoginError(
                'oidc_not_configured',
                'OIDC authorization endpoint is not configured',
                400,
            )

        callback_url = _public_oidc_url(provider.slug)
        oauth = OAuth2Session(
            client_id=provider.client_id,
            client_secret=_client_secret(provider),
            scope=provider.scope,
            redirect_uri=callback_url,
        )
        nonce = secrets.token_urlsafe(24)
        authorization_url, state = oauth.create_authorization_url(
            authorization_endpoint,
            nonce=nonce,
        )
        session[f'oidc_state:{provider.slug}'] = state
        session[f'oidc_nonce:{provider.slug}'] = nonce
        session[f'oidc_return_to:{provider.slug}'] = roxywi_auth.safe_next_url(request.args.get('next'))
        return redirect(authorization_url)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': 'oidc_provider_not_found', 'message': exc.public_message}), 404
    except OidcLoginError as exc:
        return _error_response(exc)


@bp.get('/<slug>/callback')
@oidc_subscription_required
def oidc_callback(slug: str):
    try:
        provider = oidc_sql.get_provider_by_slug(slug, enabled_only=True)
    except RoxywiResourceNotFound as exc:
        return jsonify({'status': 'failed', 'error': 'oidc_provider_not_found', 'message': exc.public_message}), 404

    if request.args.get('error'):
        return jsonify({
            'status': 'failed',
            'error': 'oidc_authorization_error',
            'message': request.args.get('error_description') or request.args.get('error'),
        }), 400

    expected_state = session.pop(f'oidc_state:{provider.slug}', None)
    expected_nonce = session.pop(f'oidc_nonce:{provider.slug}', None)
    redirect_to = session.pop(f'oidc_return_to:{provider.slug}', '/')
    if not expected_state or request.args.get('state') != expected_state:
        return jsonify({
            'status': 'failed',
            'error': 'oidc_state_invalid',
            'message': 'OIDC state is invalid or expired',
        }), 400

    try:
        metadata = _load_metadata(provider)
        token_endpoint = _endpoint(provider, metadata, 'token_endpoint', 'token_endpoint')
        if not token_endpoint:
            raise OidcLoginError(
                'oidc_not_configured',
                'OIDC token endpoint is not configured',
                400,
            )

        callback_url = _public_oidc_url(provider.slug)
        authorization_response = f"{callback_url}?{request.query_string.decode('utf-8')}"
        oauth = OAuth2Session(
            client_id=provider.client_id,
            client_secret=_client_secret(provider),
            scope=provider.scope,
            redirect_uri=callback_url,
            state=expected_state,
        )
        token = oauth.fetch_token(
            token_endpoint,
            authorization_response=authorization_response,
            timeout=10,
        )
        token_claims = _validate_id_token(provider, metadata, token, expected_nonce)
        userinfo_claims = _fetch_userinfo(provider, metadata, token)
        claims = _merge_claims(token_claims, userinfo_claims)
        user_params = complete_oidc_login(provider, claims)
    except OidcLoginError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.error('OIDC callback failed', exception=exc, provider=provider.slug)
        return jsonify({
            'status': 'failed',
            'error': 'oidc_callback_failed',
            'message': 'OIDC callback failed',
        }), 502

    logger.info(f'{user_params["name"]} login via OIDC', provider=provider.slug)
    return roxywi_auth.build_login_redirect(user_params, redirect_to)
