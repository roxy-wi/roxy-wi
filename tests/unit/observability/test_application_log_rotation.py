"""Application writers must follow rename-based rotation on Unix."""
import json
import logging
from logging.handlers import WatchedFileHandler
import os

import pytest

from app.modules.roxywi import logger, log_store


@pytest.fixture
def isolated_logger(monkeypatch, tmp_path):
    instance = logging.Logger('rotation-test')
    monkeypatch.setattr(logger, '_logger', None)
    original = logging.getLogger
    monkeypatch.setattr(logger.logging, 'getLogger',
                        lambda name=None: instance if name == 'roxy-wi' else original(name))
    monkeypatch.setattr(log_store, 'store_path', lambda: None)
    configured = logger.setup_logger(str(tmp_path))
    yield configured
    for handler in configured.handlers:
        handler.close()


def test_file_logging_retains_structured_unicode_output(isolated_logger, tmp_path):
    isolated_logger.info('Certificate renewed — обновлён')
    record = json.loads((tmp_path / 'roxy-wi.log').read_text(encoding='utf-8'))
    assert record['message'] == 'Certificate renewed — обновлён'
    assert record['level'] == 'INFO'
    if os.name == 'posix':
        assert isinstance(isolated_logger.handlers[0], WatchedFileHandler)


def test_package_retention_does_not_remove_shared_log_files(monkeypatch):
    from app import jobs
    monkeypatch.setattr(jobs.get_config, 'get_config_var', lambda *args: 'package')
    monkeypatch.setattr(jobs, '_run_database_job',
                        lambda *args: pytest.fail('Application attempted package log cleanup'))
    jobs.delete_old_logs()


@pytest.mark.skipif(os.name != 'posix', reason='Unix inode rotation semantics')
def test_each_writer_reopens_after_rotation(isolated_logger, tmp_path):
    current = tmp_path / 'roxy-wi.log'
    second = WatchedFileHandler(current, encoding='utf-8')
    try:
        isolated_logger.info('before rotation')
        current.rename(tmp_path / 'roxy-wi.log.1')
        current.touch(mode=0o640)
        isolated_logger.info('after rotation')
        second.emit(logging.LogRecord('second', logging.INFO, '', 0, 'second writer', (), None))
        archived = (tmp_path / 'roxy-wi.log.1').read_text()
        active = current.read_text()
        assert 'before rotation' in archived and 'after rotation' not in archived
        assert 'after rotation' in active and 'second writer' in active
    finally:
        second.close()
