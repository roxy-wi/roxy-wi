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
