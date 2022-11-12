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
        try:
            cur_time_zone = timezone(self.time_zone)
        except Exception:
            cur_time_zone = timezone('UTC')

        if kwargs.get('timedelta'):
            now_utc = datetime.now(cur_time_zone) + timedelta(days=kwargs.get('timedelta'))
        elif kwargs.get('timedelta_minus'):
            now_utc = datetime.now(cur_time_zone) - timedelta(days=kwargs.get('timedelta_minus'))
        elif kwargs.get('timedelta_minutes'):
            now_utc = datetime.now(cur_time_zone) + timedelta(minutes=kwargs.get('timedelta_minutes'))
        elif kwargs.get('timedelta_minutes_minus'):
            now_utc = datetime.now(cur_time_zone) - timedelta(minutes=kwargs.get('timedelta_minutes_minus'))
        else:
            now_utc = datetime.now(cur_time_zone)

        if log_type == 'config':
            self.fmt = "%Y-%m-%d.%H:%M:%S"
        elif log_type == 'logs':
            self.fmt = '%Y%m%d'
        elif log_type == "date_in_log":
            self.fmt = "%b %d %H:%M:%S"
        elif log_type == 'regular':
            self.fmt = "%Y-%m-%d %H:%M:%S"

        return now_utc.strftime(self.fmt)


class Tools:
    @staticmethod
    def get_hash(need_hashed):
        if need_hashed is None:
            return need_hashed
        import hashlib
        h = hashlib.md5(need_hashed.encode('utf-8'))
        p = h.hexdigest()
        return p