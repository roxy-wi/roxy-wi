import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path(tempfile.mkdtemp(prefix='roxywi-tests-'))

os.environ.update({
    'ROXYWI_TESTING': '1',
    'ROXYWI_CONFIG_FILE': str(PROJECT_ROOT / 'tests' / 'fixtures' / 'roxy-wi.cfg'),
    'ROXYWI_DB_PATH': str(RUNTIME_DIR / 'roxy-wi.db'),
    'ROXYWI_LOG_PATH': str(RUNTIME_DIR / 'logs'),
    'ROXYWI_SECRET_KEY': 'test-only-flask-secret-key-with-at-least-32-chars',
    'ROXYWI_JWT_ALGORITHM': 'HS256',
    'ROXYWI_JWT_SECRET_KEY': 'test-only-jwt-secret-key-with-at-least-32-chars',
    'ROXYWI_BOOTSTRAP_ADMIN_PASSWORD': 'TestBootstrapPassword!',
    'ROXYWI_SECRET_PHRASE': 'E2nCq8NnECvPQ5zUQntL_-Nt-qBncYkrEmMkYGzVpyM=',
})


import pytest

from app import app as flask_app


@pytest.fixture(scope='session')
def app():
    flask_app.config.update(TESTING=True, JWT_COOKIE_SECURE=False, SESSION_COOKIE_SECURE=False)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
