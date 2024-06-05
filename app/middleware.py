from functools import wraps

from flask import redirect, url_for, abort, g

import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common


def check_services(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        service = kwargs['service']
        if service not in ('haproxy', 'nginx', 'apache', 'keepalived', 'cluster', 'waf', 'udp'):
            abort(405, 'Wrong service')
        if not roxywi_auth.is_access_permit_to_service(service):
            abort(403, f'You do not have needed permissions to access to {service.title()} service')
        return fn(*args, **kwargs)
    return decorated_view


def get_user_params(virt=0, disable=0):
    def inner_decorator(fn):
        @wraps(fn)
        def decorated_views(*args, **kwargs):
            try:
                user_params = roxywi_common.get_users_params(virt=virt, disable=disable, service=kwargs.get('service'))
                g.user_params = user_params
            except Exception:
                return redirect(url_for('login_page'))
            return fn(*args, **kwargs)
        return decorated_views
    return inner_decorator
