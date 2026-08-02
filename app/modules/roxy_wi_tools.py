from datetime import datetime, timedelta

from pytz import timezone
import configparser
import os

from werkzeug.security import check_password_hash, generate_password_hash


class GetConfigVar:
    def __init__(self):
        self.path_config = os.environ.get("ROXYWI_CONFIG_FILE", "/etc/roxy-wi/roxy-wi.cfg")
        self.config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        self.config.read(self.path_config)

    def get_config_var(self, sec, var):
        try:
            return self.config.get(sec, var)
        except configparser.Error as e:
            print(f'error: in the config file: {self.path_config}: {e}')
        except Exception as e:
            print(f'Check the config file. Presence section {sec} and parameter {var}')
            print(e)
            return


class GetDate:
    def __init__(self, time_zone=None):
        self.time_zone = time_zone
        self.fmt = "%Y-%m-%d.%H:%M:%S"

    def return_date(self, log_type, **kwargs):
        if self.time_zone:
            cur_time_zone = timezone(self.time_zone)
        else:
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
        return generate_password_hash(need_hashed)

    @staticmethod
    def check_password(password, password_hash):
        """Return (matches, needs_rehash), accepting legacy MD5 hashes once."""
        if not password_hash:
            return False, False

        import hashlib
        import hmac
        import re

        if re.fullmatch(r"[0-9a-fA-F]{32}", password_hash):
            legacy_hash = hashlib.md5(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(legacy_hash, password_hash.lower()), True

        try:
            return check_password_hash(password_hash, password), False
        except (ValueError, TypeError):
            return False, False
