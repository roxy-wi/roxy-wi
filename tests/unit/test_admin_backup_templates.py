import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


def _remote_backup():
    return SimpleNamespace(
        id=1,
        server_id=1,
        rserver='backup.example.test',
        rpath='/srv/backup',
        type='backup',
        time='daily',
        cred_id=1,
        description='Remote backup',
    )


def _s3_backup():
    return SimpleNamespace(
        id=2,
        server_id=1,
        server='server-1',
        s3_server='s3.example.test',
        bucket='configs',
        time='daily',
        description='S3 backup',
    )


def _git_backup():
    return SimpleNamespace(
        id=3,
        server_id=1,
        service_id=1,
        period='daily',
        repo='ssh://git.example.test/configs.git',
        branch='main',
        cred_id=1,
        description='Git backup',
    )


def _render_backup_tab(app, **overrides):
    context = dict(
        lang='en',
        is_needed_tool=True,
        user_subscription={'user_status': 1, 'user_plan': 'support'},
        user_status=1,
        user_plan='support',
        servers=[(1, 'server-1')],
        services=[SimpleNamespace(service_id=1, service='haproxy')],
        sshs=[],
        backups=[_remote_backup()],
        s3_backups=[_s3_backup()],
        gits=[_git_backup()],
    )
    context.update(overrides)
    return app.jinja_env.get_template('include/admin_backup.html').render(**context)


def test_backup_tab_renders_nested_action_templates_with_imported_language(app):
    rendered = _render_backup_tab(app)

    assert rendered.count('admin-actions-toggle') == 3
    assert 'cloneBackup(1)' in rendered
    assert 'cloneS3Backup(2)' in rendered
    assert 'confirmDeleteGit(3)' in rendered


def test_backup_ajax_partials_accept_language_code(app):
    remote = app.jinja_env.get_template('ajax/new_backup.html').render(
        lang='en', backups=[_remote_backup()], servers=[(1, 'server-1')], sshs=[]
    )
    s3 = app.jinja_env.get_template('ajax/new_s3_backup.html').render(
        lang='en', backups=[_s3_backup()]
    )
    git = app.jinja_env.get_template('ajax/new_git.html').render(
        lang='en',
        gits=[_git_backup()],
        servers=[(1, 'server-1')],
        services=[SimpleNamespace(service_id=1, service='haproxy')],
        sshs=[],
        new_add=1,
    )

    for rendered in (remote, s3, git):
        assert 'admin-actions-toggle' in rendered
        assert 'admin-actions-menu' in rendered
    assert 'backup.example.test' in remote


def test_backup_schedule_status_shows_migration_and_run_history(app):
    backup = _remote_backup()
    backup.schedule_state = {'migration_required': True}
    template = app.jinja_env.get_template('include/backup_schedule_status.html')
    assert 'Waiting for schedule migration' in template.render(b=backup)
    backup.schedule_state = {'migration_required': False, 'next_run_at': '2026-09-17T00:00:00Z',
                             'retry_at': None, 'last_task_id': 42, 'last_status': 'failed'}
    rendered = template.render(b=backup)
    assert '2026-09-17 00:00:00 UTC' in rendered
    assert 'failed (operation #42)' in rendered
