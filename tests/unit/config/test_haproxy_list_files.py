from types import SimpleNamespace

import pytest

from app.scripts import haproxy_lists as files


def test_compare_and_replace_rejects_changed_file_and_configuration(tmp_path):
    path = tmp_path / 'black/example.lst'
    files.write_file(path, '192.0.2.1\n')
    config = tmp_path / 'haproxy.cfg'
    config.write_text('frontend public\n')
    request = dict(root=str(tmp_path), color='black', name=path.name, operation='save',
                   content='192.0.2.2\n', expected=files.digest('192.0.2.1\n'),
                   expected_configs={str(config): files.digest('frontend public\n')})
    path.write_text('192.0.2.3\n')
    assert files.change_file(request) == {'error': 'changed'}
    path.write_text('192.0.2.1\n')
    config.write_text('frontend changed\n')
    assert files.change_file(request) == {'error': 'changed'}
    assert path.read_text() == '192.0.2.1\n'


def test_failed_atomic_write_keeps_previous_file(tmp_path, monkeypatch):
    path = tmp_path / 'black/example.lst'
    files.write_file(path, '192.0.2.1\n')
    monkeypatch.setattr(files.os, 'replace', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        files.write_file(path, '192.0.2.2\n')
    assert path.read_text() == '192.0.2.1\n'
    assert list(path.parent.iterdir()) == [path]


def test_missing_and_empty_files_have_different_revisions():
    assert files.digest(None) != files.digest('')


def test_container_path_uses_persistent_directory_and_rejects_file_mount(tmp_path, monkeypatch):
    directory = tmp_path / 'managed'
    files.write_file(directory / 'black/example.lst', '192.0.2.1\n')
    mounts = [dict(Type='bind', RW=True, Source=str(directory), Destination='/etc/haproxy')]
    monkeypatch.setattr(files, 'module', SimpleNamespace(container_state=lambda *args: {'Mounts': mounts}), raising=False)
    data = dict(root=str(directory), files=[], main=str(directory / 'haproxy.cfg'), container='proxy',
                runtime={'engine': 'podman', 'owner': 'operator'}, color='black', name='example.lst')
    result = files.inspect_files(data)
    assert result['content'] == '192.0.2.1\n'
    assert result['runtime_root'].replace('\\', '/') == '/etc/haproxy'
    mounts.append(dict(Type='bind', RW=True, Source=str(directory / 'black/example.lst'),
                       Destination='/etc/haproxy/black/example.lst'))
    with pytest.raises(ValueError, match='persistent_mount_required'):
        files.inspect_files(data)


@pytest.mark.parametrize('name', ['../example.lst', 'other/example.lst', 'example.cfg'])
def test_remote_list_path_cannot_escape_managed_directory(tmp_path, name):
    with pytest.raises(ValueError, match='invalid_path'):
        files.list_path(tmp_path, 'black', name)
