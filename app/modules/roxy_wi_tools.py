from datetime import datetime, timedelta

from pytz import timezone
from configparser import ConfigParser, ExtendedInterpolation


class GetConfigVar:
    def __init__(self):
        self.path_config = "/etc/roxy-wi/roxy-wi.cfg"
        self.config = ConfigParser(interpolation=ExtendedInterpolation())
        self.config.read(self.path_config)

    def get_config_var(self, sec, var):
        try:
            return self.config.get(sec, var)
        except Exception as e:
            print('Content-type: text/html\n')
            print(
                f'<center><div class="alert alert-danger">Check the config file. Presence section {sec} and parameter {var}</div>')
            print(e)
            return


class GetDate:
    def __init__(self, time_zone):
        self.time_zone = time_zone
        self.fmt = "%Y-%m-%d.%H:%M:%S"

    def return_date(self, log_type, **kwargs):
        if kwargs.get('timedelta'):
            try:
                now_utc = datetime.now(timezone(self.time_zone)) + timedelta(days=kwargs.get('timedelta'))
            except Exception:
                now_utc = datetime.now(timezone('UTC')) + timedelta(days=kwargs.get('timedelta'))
        elif kwargs.get('timedelta_minus'):
            try:
                now_utc = datetime.now(timezone(self.time_zone)) - timedelta(
                    days=kwargs.get('timedelta_minus'))
            except Exception:
                now_utc = datetime.now(timezone('UTC')) - timedelta(days=kwargs.get('timedelta_minus'))
        elif kwargs.get('timedelta_minutes'):
            try:
                now_utc = datetime.now(timezone(self.time_zone)) + timedelta(
                    minutes=kwargs.get('timedelta_minutes'))
            except Exception:
                now_utc = datetime.now(timezone('UTC')) + timedelta(minutes=kwargs.get('timedelta_minutes'))
        elif kwargs.get('timedelta_minutes_minus'):
            try:
                now_utc = datetime.now(timezone(self.time_zone)) - timedelta(
                    minutes=kwargs.get('timedelta_minutes_minus'))
            except Exception:
                now_utc = datetime.now(timezone('UTC')) - timedelta(minutes=kwargs.get('timedelta_minutes_minus'))
        else:
            try:
                now_utc = datetime.now(timezone(self.time_zone))
            except Exception:
                now_utc = datetime.now(timezone('UTC'))

        if log_type == 'config':
            self.fmt = "%Y-%m-%d.%H:%M:%S"
        elif log_type == 'logs':
            self.fmt = '%Y%m%d'
        elif log_type == "date_in_log":
            self.fmt = "%b %d %H:%M:%S"
        elif log_type == 'regular':
            self.fmt = "%Y-%m-%d %H:%M:%S"

        return now_utc.strftime(self.fmt)
