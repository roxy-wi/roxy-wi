from datetime import datetime, timedelta, timezone

from app.modules.common import common


def test_time_zoned_date_accepts_database_fractional_seconds(monkeypatch):
    monkeypatch.setattr(common.sql, 'get_setting', lambda _name: 'UTC')

    assert common.get_time_zoned_date(
        '2026-09-02 06:01:08.428310',
        '%Y-%m-%d %H:%M:%S.%f',
    ) == '2026-09-02 06:01:08.428310'


def test_time_zoned_date_accepts_worker_iso_timestamp(monkeypatch):
    monkeypatch.setattr(common.sql, 'get_setting', lambda _name: 'Europe/Moscow')

    assert common.get_time_zoned_date(
        '2026-09-02T06:01:08.428310Z',
        '%Y-%m-%d %H:%M:%S',
    ) == '2026-09-02 09:01:08'


def test_time_zoned_date_preserves_aware_datetime_instant(monkeypatch):
    monkeypatch.setattr(common.sql, 'get_setting', lambda _name: 'UTC')
    source = datetime(
        2026,
        9,
        2,
        9,
        1,
        8,
        tzinfo=timezone(timedelta(hours=3)),
    )

    assert common.get_time_zoned_date(source) == '2026-09-02 06:01:08'


def test_checker_history_date_format_accepts_fractional_seconds(monkeypatch):
    monkeypatch.setattr(common.sql, 'get_setting', lambda _name: 'UTC')

    assert common.get_time_zoned_date(
        '2026-09-02 06:01:08.428310',
        '%Y %m %d',
    ) == '2026 09 02'
