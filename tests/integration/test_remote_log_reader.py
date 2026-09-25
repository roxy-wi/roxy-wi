"""Exercise the real standalone SSH helper on local files (no Flask/SSH needed).

Also runnable on an isolated Linux host: python3 tests/integration/test_remote_log_reader.py
"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[2] / 'app' / 'scripts' / 'log_reader.py'
spec = importlib.util.spec_from_file_location('remote_log_reader', HELPER)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def lines(result):
    return base64.b64decode(result['data']).decode('utf-8').splitlines()


class RemoteLogReaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'access.log'
        self.path.write_bytes(b'old\n')

    def read(self, previous=None, limit=100):
        return reader.read_log(str(self.path), previous['position'] if previous else None, limit)

    def append(self, data, path=None):
        with (path or self.path).open('ab') as stream:
            stream.write(data)

    def test_append_repeated_lines_and_partial_utf8(self):
        first = self.read()
        self.assertEqual(lines(first), ['old'])
        self.append(b'same\nsame\n' + 'Ошибка'.encode()[:-1])
        second = self.read(first)
        self.assertEqual(lines(second), ['same', 'same'])
        self.assertFalse(second['more'])
        self.assertEqual(lines(self.read(second)), [])
        self.append('Ошибка'.encode()[-1:] + b'\n')
        third = self.read(second)
        self.assertEqual(lines(third), ['Ошибка'])
        self.assertEqual(lines(self.read(third)), [])

    def test_limit_drains_backlog_without_dropping_or_deduplicating(self):
        cursor = self.read()
        self.append(b'same\n' * 8)
        found = []
        for _ in range(4):
            cursor = self.read(cursor, limit=2)
            found.extend(lines(cursor))
        self.assertEqual(found, ['same'] * 8)
        self.assertFalse(cursor['more'])

    def test_rename_and_late_append_to_rotated_file(self):
        first = self.read()
        rotated = self.root / 'access.log.1'
        self.path.rename(rotated)
        self.append(b'old writer\n', rotated)
        self.path.write_bytes(b'new writer\n')
        second = self.read(first, limit=1)
        self.assertEqual(lines(second), ['old writer'])
        self.assertTrue(second['more'])
        third = self.read(second)
        self.assertEqual(lines(third), ['new writer'])
        self.assertFalse(third['reset'])
        self.append(b'late writer\n', rotated)
        fourth = self.read(third)
        self.assertEqual(lines(fourth), ['late writer'])

    def test_several_rotations_between_polls(self):
        first = self.read()
        self.append(b'before rotation\n')
        self.path.rename(self.root / 'access.log.2')
        (self.root / 'access.log.1').write_bytes(b'intermediate\n')
        self.path.write_bytes(b'current\n')
        second = self.read(first)
        self.assertEqual(lines(second), ['before rotation', 'intermediate', 'current'])

    def test_copytruncate_recovers_unread_copy_without_duplicate_history(self):
        first = self.read()
        self.append(b'unread before truncate\n')
        shutil.copyfile(self.path, self.root / 'access.log.1')
        self.path.write_bytes(b'new after truncate and longer than old\n')
        second = self.read(first)
        self.assertEqual(lines(second), ['unread before truncate', 'new after truncate and longer than old'])
        self.assertTrue(second['reset'])
        self.assertEqual(lines(self.read(second)), [])

    def test_same_inode_overwrite_larger_than_previous_size(self):
        first = self.read()
        self.path.write_bytes(b'longer replacement\n')
        second = self.read(first)
        self.assertTrue(second['reset'])
        self.assertEqual(lines(second), ['longer replacement'])

    def test_rotation_gap_then_new_file(self):
        first = self.read()
        self.path.rename(self.root / 'access.log.1')
        gap = self.read(first)
        self.assertFalse(gap['reset'])
        self.assertEqual(lines(gap), [])
        self.path.write_bytes(b'after gap\n')
        self.assertEqual(lines(self.read(gap)), ['after gap'])

    def test_unavailable_rotated_file_reports_gap(self):
        first = self.read()
        self.path.unlink()
        self.path.write_bytes(b'new file\n')
        second = self.read(first)
        self.assertTrue(second['reset'])
        self.assertEqual(lines(second), ['new file'])

    def test_existing_archives_are_not_replayed(self):
        (self.root / 'access.log.1').write_bytes(b'historical\n')
        (self.root / 'access.log.2.gz').write_bytes(b'not readable gzip')
        first = self.read()
        self.assertEqual(lines(first), ['old'])
        self.assertEqual(lines(self.read(first)), [])

    def test_tail_starts_at_record_boundary_and_reports_limit(self):
        self.path.write_bytes(b'old prefix\nlast\n')
        with patch.object(reader, 'SNAPSHOT_BYTES', 8):
            first = self.read()
        self.assertTrue(first['limited'])
        self.assertEqual(lines(first), ['last'])

    def test_oversized_line_is_skipped_in_full_then_reading_continues(self):
        cursor = self.read()
        self.append(b'x' * 140 + b'not a new record\nok\n')
        found, limited = [], False
        with patch.object(reader, 'FOLLOW_BYTES', 50), patch.object(reader, 'MAX_LINE', 30):
            for _ in range(5):
                cursor = self.read(cursor)
                found.extend(lines(cursor))
                limited |= cursor['limited']
        self.assertEqual(found, ['ok'])
        self.assertTrue(limited)
        self.assertFalse(cursor['more'])

    def test_chunk_boundary_with_partial_line_still_drains_backlog(self):
        first = self.read()
        self.append(b'one\ntwo\nthree\n')
        with patch.object(reader, 'FOLLOW_BYTES', 7):
            second = self.read(first)
            self.assertEqual(lines(second), ['one'])
            self.assertTrue(second['more'])
            third = self.read(second)
            self.assertEqual(lines(third), ['two'])
            self.assertTrue(third['more'])
            fourth = self.read(third)
        self.assertEqual(lines(fourth), ['three'])
        self.assertFalse(fourth['more'])

    def test_initial_record_count_is_bounded(self):
        self.path.write_bytes(b'a\nb\nc\n')
        with patch.object(reader, 'MAX_INITIAL_RECORDS', 2):
            first = self.read()
        self.assertTrue(first['limited'])
        self.assertEqual(lines(first), ['b', 'c'])

    def test_rewrite_during_read_retries_instead_of_signing_wrong_position(self):
        original = reader.anchor
        def changed(stream, offset):
            self.path.write_bytes(b'new\n')
            return original(stream, offset)
        with patch.object(reader, 'anchor', changed):
            with self.assertRaises(OSError):
                self.read()

    @unittest.skipUnless(os.name == 'posix', 'Linux hard links')
    def test_hardlinks_do_not_duplicate_records(self):
        first = self.read()
        rotated = self.root / 'access.log.1'
        self.path.rename(rotated)
        os.link(rotated, self.root / 'access.log.2')
        self.append(b'once\n', rotated)
        self.path.write_bytes(b'current\n')
        self.assertEqual(lines(self.read(first)), ['once', 'current'])

    @unittest.skipUnless(os.name == 'posix', 'Linux file semantics')
    def test_symlink_fifo_and_directory_are_rejected(self):
        for kind in ('symlink', 'fifo', 'directory'):
            with self.subTest(kind=kind):
                target = self.root / kind
                if kind == 'symlink':
                    target.symlink_to(self.path)
                elif kind == 'fifo':
                    os.mkfifo(target)
                else:
                    target.mkdir()
                result = subprocess.run([sys.executable, str(HELPER)],
                    input=json.dumps({'path': str(target)}), capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout), {'error': 'Cannot read the service log'})
                self.assertEqual(result.stderr, '')

    def test_real_stdin_protocol_and_no_installation(self):
        self.path = self.root / 'log file ; literal $(echo test).log'
        self.path.write_bytes(b'protocol\n')
        result = subprocess.run([sys.executable, '-c', HELPER.read_text(encoding='utf-8')],
            input=json.dumps({'path': str(self.path)}), capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        first = json.loads(result.stdout)
        self.assertEqual(lines(first), ['protocol'])
        self.append(b'next\n')
        result = subprocess.run([sys.executable, '-c', HELPER.read_text(encoding='utf-8')],
            input=json.dumps({'path': str(self.path), 'position': first['position']}),
            capture_output=True, text=True, timeout=3)
        self.assertEqual(lines(json.loads(result.stdout)), ['next'])
        self.assertEqual(len(list(self.root.iterdir())), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
