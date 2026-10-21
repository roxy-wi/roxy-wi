from pathlib import Path

import pytest
from flask import Flask, abort, g, jsonify, render_template
from flask_pydantic.exceptions import ValidationError
from peewee import OperationalError
from werkzeug.exceptions import HTTPException, ServiceUnavailable, TooManyRequests

from app.modules.roxywi import error_handler
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiPermissionError


HTML = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
LOCALES = ('en', 'ru', 'fr', 'pt-br', 'es-ES', 'zh')


@pytest.fixture
def error_app(app):
    """Real error dispatch and templates without database or authentication fixtures."""
    instance = Flask(__name__, template_folder=str(Path(app.root_path) / 'templates'),
                     static_folder=str(Path(app.root_path) / 'static'), static_url_path='/static')
    instance.config['TESTING'] = True
    instance.add_url_rule('/overview', endpoint='overview.index', view_func=lambda: 'Overview')
    instance.add_url_rule('/login', endpoint='login_page', view_func=lambda: 'Login')

    @instance.get('/http/<int:code>')
    @instance.get('/api/http/<int:code>')
    @instance.get('/health/http/<int:code>')
    def http_error(code):
        if code in (402, 507):
            error = HTTPException(description='internal-sensitive-detail')
            error.code = code
            raise error
        if code == 429:
            raise TooManyRequests(retry_after=30)
        if code == 503:
            raise ServiceUnavailable(retry_after=60)
        abort(code, description='internal-sensitive-detail')

    @instance.get('/failure/<kind>')
    def failure(kind):
        if kind == 'missing':
            raise RoxywiResourceNotFound('internal-sensitive-detail')
        if kind == 'forbidden':
            raise RoxywiPermissionError('internal-sensitive-detail')
        if kind == 'validation':
            raise ValidationError(body_params=[{'loc': ['field'], 'msg': 'Invalid field'}])
        if kind == 'context':
            g.user_params = {'user': 'admin'}
            return render_template('error.html')
        raise OperationalError('internal-sensitive-detail')

    @instance.context_processor
    def broken_context_processor():
        raise OperationalError('internal-sensitive-detail')

    @instance.route('/direct/<int:code>', methods=['GET', 'POST'])
    @instance.get('/api/direct/<int:code>')
    def direct_error(code):
        response = jsonify(status='failed', error='internal-sensitive-detail')
        response.status_code = code
        response.headers['Retry-After'] = '10'
        return response

    @instance.get('/public-error')
    def public_error():
        return error_handler.error_response('Safe <script>detail</script>', 500,
                                            public_message='Safe <script>detail</script>')

    error_handler.register_error_handlers(instance)
    return instance


@pytest.mark.parametrize('code', [400, 402, 403, 404, 405, 408, 409, 410, 413, 415, 416, 422, 429,
                                 500, 501, 502, 503, 504, 507])
def test_http_errors_render_html_with_original_status(error_app, code):
    response = error_app.test_client().get(f'/http/{code}', headers=HTML)
    assert response.status_code == code
    assert response.mimetype == 'text/html'
    assert f'<p class="error-code">{code}</p>' in response.text
    assert 'internal-sensitive-detail' not in response.text
    assert 'Cache-Control' in response.headers and response.cache_control.no_store
    assert 'Accept' in response.vary
    if code in (429, 503):
        assert response.headers['Retry-After'] == ('30' if code == 429 else '60')


@pytest.mark.parametrize('kind,status', [('missing', 404), ('forbidden', 403), ('validation', 400),
                                        ('database', 500), ('context', 500)])
def test_domain_and_unhandled_errors_render_without_database_or_context_processors(error_app, monkeypatch, kind, status):
    logged = []
    monkeypatch.setattr(error_handler, 'log_error', lambda *args, **kwargs: logged.append(args[0]))
    response = error_app.test_client().get('/failure/' + kind, headers=HTML)
    assert response.status_code == status
    assert response.mimetype == 'text/html'
    assert 'internal-sensitive-detail' not in response.text
    assert len(logged) == (0 if kind == 'validation' else 1)


@pytest.mark.parametrize('headers', [
    {}, {'Accept': '*/*'}, {'Accept': 'application/json'},
    {'Accept': 'text/html;q=0'},
    {'Accept': 'application/json;q=0.9,text/html;q=0.5'},
    {**HTML, 'X-Requested-With': 'XMLHttpRequest'},
    {**HTML, 'Sec-Fetch-Mode': 'cors'}, {**HTML, 'Sec-Fetch-Mode': 'same-origin'},
    {**HTML, 'Content-Type': 'application/json'},
])
@pytest.mark.parametrize('path', ['/http/404', '/failure/missing', '/direct/404'])
def test_api_and_background_error_contract_is_preserved(error_app, path, headers):
    response = error_app.test_client().get(path, headers=headers)
    assert response.status_code == 404
    assert response.is_json
    assert response.json['status'] == 'failed'
    assert response.json['error']


@pytest.mark.parametrize('path', ['/api/http/503', '/health/http/503', '/api/direct/503', '/api', '/health'])
def test_api_and_health_stay_json_even_when_html_is_accepted(error_app, path):
    response = error_app.test_client().get(path, headers=HTML)
    assert response.is_json
    assert response.status_code == (503 if path.endswith('503') else 404)


@pytest.mark.parametrize('code', [401, 403, 404, 500, 503, 599])
def test_direct_json_errors_become_pages_without_exposing_payload(error_app, code):
    response = error_app.test_client().get(f'/direct/{code}', headers=HTML)
    assert response.status_code == code and response.mimetype == 'text/html'
    assert f'<p class="error-code">{code}</p>' in response.text
    assert 'internal-sensitive-detail' not in response.text
    assert response.headers['Retry-After'] == '10'


def test_page_posts_are_not_retried_and_api_posts_keep_json(error_app):
    client = error_app.test_client()
    page = client.post('/direct/500', data={'field': 'value'}, headers=HTML)
    assert page.status_code == 500 and page.mimetype == 'text/html'
    assert '<form' not in page.text and 'location.reload' not in page.text
    api = client.post('/direct/500', json={'field': 'value'}, headers=HTML)
    assert api.status_code == 500 and api.is_json


def test_method_headers_and_head_requests_are_preserved(error_app):
    client = error_app.test_client()
    for headers in (HTML, {'Accept': 'application/json'}):
        response = client.post('/overview', headers=headers)
        assert response.status_code == 405 and 'GET' in response.allow
    response = client.head('/http/404', headers=HTML)
    assert response.status_code == 404 and not response.data


@pytest.mark.parametrize('locale', LOCALES)
def test_all_translations_are_complete_and_used(error_app, locale):
    english = error_app.jinja_env.get_template('languages/en.html').module.http_errors
    messages = error_app.jinja_env.get_template(f'languages/{locale}.html').module.http_errors
    assert set(messages) == set(english)
    assert all(isinstance(value, str) and value.strip() for value in messages.values())
    client = error_app.test_client()
    client.set_cookie('lang', locale)
    response = client.get('/http/404', headers=HTML)
    assert f'<html lang="{locale}">' in response.text
    assert messages['404_title'] in response.text
    assert messages['overview'] in response.text


@pytest.mark.parametrize('locale', ['unsupported', '../../error', ''])
def test_invalid_language_cookie_falls_back_to_english(error_app, locale):
    client = error_app.test_client()
    client.set_cookie('lang', locale)
    response = client.get('/http/500', headers=HTML)
    assert response.status_code == 500
    assert '<html lang="en">' in response.text and 'Something went wrong' in response.text


def test_only_explicit_public_details_are_shown_and_escaped(error_app):
    response = error_app.test_client().get('/public-error', headers=HTML)
    assert response.status_code == 500
    assert 'Safe &lt;script&gt;detail&lt;/script&gt;' in response.text
    assert '<script>detail</script>' not in response.text


def test_real_missing_waf_rule_and_route_render_pages(product_client, product):
    for path in [f'/waf/haproxy/{product.server.ip}/rule/999999', '/missing-page-for-error-test']:
        response = product_client.get(path, headers=HTML)
        assert response.status_code == 404 and response.mimetype == 'text/html'
        assert 'Page not found' in response.text
    api = product_client.get('/api/missing-page-for-error-test', headers=HTML)
    assert api.status_code == 404 and api.is_json


def test_real_login_redirect_and_ajax_401_still_work(client, product):
    response = client.get('/overview', headers=HTML)
    assert response.status_code == 302 and response.location.startswith('/login?next=')
    response = client.get('/overview', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 401 and response.is_json


def test_real_readiness_remains_json(client, monkeypatch):
    monkeypatch.setattr('app.routes.health.routes.database_readiness.get', lambda: (False, 'unavailable'))
    response = client.get('/health/ready', headers=HTML)
    assert response.status_code == 503 and response.json['status'] == 'unavailable'
