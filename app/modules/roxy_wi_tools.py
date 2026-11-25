from datetime import datetime, timedelta
from functools import lru_cache

from pytz import timezone
import configparser
import os
import re

from werkzeug.security import check_password_hash, generate_password_hash


class GetConfigVar:
    def __init__(self):
        self.path_config = os.environ.get("ROXYWI_CONFIG_FILE", "/etc/roxy-wi/roxy-wi.cfg")
        self.config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        self.config.read(self.path_config)

    @staticmethod
    def _environment_names(sec, var):
        """Return backwards-compatible environment names for a cfg option."""
        section = re.sub(r'[^A-Za-z0-9]+', '_', str(sec)).strip('_').upper()
        option = re.sub(r'[^A-Za-z0-9]+', '_', str(var)).strip('_').upper()
        names = [f'ROXYWI_{section}_{option}']
        # Historically the main section was exposed without a MAIN prefix.
        # Supporting the short form for every section also keeps container
        # configuration readable (ROXYWI_LIB_PATH, ROXYWI_MYSQL_HOST, ...).
        short_name = f'ROXYWI_{option}'
        if short_name not in names:
            names.append(short_name)
        return names

    def get_config_var(self, sec, var, default=None, use_environment=True):
        if use_environment:
            for environment_name in self._environment_names(sec, var):
                if environment_name in os.environ:
                    return os.environ[environment_name]
        try:
            return self.config.get(sec, var)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default
        except configparser.Error as error:
            raise RuntimeError(f'Invalid config file {self.path_config}: {error}') from error

    def find_config_var(self, var, default=None):
        """Find an option in any cfg section after checking its ENV override."""
        option = re.sub(r'[^A-Za-z0-9]+', '_', str(var)).strip('_').upper()
        environment_name = f'ROXYWI_{option}'
        if environment_name in os.environ:
            return os.environ[environment_name]
        for section in self.config.sections():
            if self.config.has_option(section, var):
                return self.config.get(section, var)
        return default


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


@lru_cache(maxsize=1)
def _legacy_password_verifier():
    # libpass defaults to4096 characters. Preserve passwords already accepted by
    # the web request body limit, using its documented pre-import setting only.
    # An explicit operator-provided Passlib bound remains authoritative. This
    # must precede the first Passlib import; an already-loaded provider retains
    # its original limit rather than having private globals changed here.
    bound = GetConfigVar().get_config_var('main', 'max_content_length', str(16 * 1024 * 1024))
    os.environ.setdefault('PASSLIB_MAX_PASSWORD_SIZE', str(bound))
    from passlib.hash import hex_md5
    return hex_md5


class Tools:
    @staticmethod
    def get_hash(need_hashed):
        if need_hashed is None:
            return need_hashed
        return generate_password_hash(need_hashed)

    @staticmethod
    def check_password(password, password_hash):
        """Return (matches, needs_rehash), accepting legacy MD5 hashes once."""
        if not isinstance(password, str) or not isinstance(password_hash, str) or not password_hash:
            return False, False

        if re.fullmatch(r"[0-9a-fA-F]{32}", password_hash):
            # Verify existing legacy rows only; never create a new legacy hash.
            # Successful password login still upgrades via the identity/password CAS.
            try:
                return _legacy_password_verifier().verify(password, password_hash), True
            except (ValueError, TypeError):
                # Includes an unavailable/disabled backend and an explicit size
                # bound. Deny without bypassing system cryptographic policy.
                return False, True

        try:
            return check_password_hash(password_hash, password), False
        except (ValueError, TypeError):
            return False, False
