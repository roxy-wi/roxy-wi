from flask import render_template, request, g
from flask_login import login_required

from app.routes.checker import bp
from app.middleware import get_user_params
import app.modules.db.history as history_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.tools.checker as checker_mod


@bp.before_request
@login_required
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/settings')
@get_user_params()
def checker_settings():
    roxywi_common.check_user_group_for_flask()

    return render_template('checker.html')


@bp.post('/settings/update')
def update_settings():
    service = request.form.get('service')
    setting_id = int(request.form.get('setting_id'))
    email = int(request.form.get('email'))
    service_alert = int(request.form.get('server'))
    telegram_id = int(request.form.get('telegram_id'))
    slack_id = int(request.form.get('slack_id'))
    pd_id = int(request.form.get('pd_id'))

    if service == 'haproxy':
        maxconn_alert = int(request.form.get('maxconn'))
        backend_alert = int(request.form.get('backend'))
        return checker_mod.update_haproxy_settings(
            setting_id, email, service_alert, backend_alert, maxconn_alert, telegram_id, slack_id, pd_id
        )
    elif service in ('nginx', 'apache'):
        return checker_mod.update_service_settings(setting_id, email, service_alert, telegram_id, slack_id, pd_id)
    else:
        backend_alert = int(request.form.get('backend'))
        return checker_mod.update_keepalived_settings(setting_id, email, service_alert, backend_alert, telegram_id, slack_id, pd_id)


@bp.route('/settings/load')
@get_user_params()
def load_checker():
    return checker_mod.load_checker()


@bp.route('/history')
@get_user_params()
def checker_history():
    roxywi_common.check_user_group_for_flask()

    kwargs = {
        'lang': g.user_params['lang'],
        'smon': history_sql.alerts_history('Checker', g.user_params['group_id']),
        'user_subscription': roxywi_common.return_user_subscription(),
        'action': 'checker'
    }

    return render_template('smon/checker_history.html', **kwargs)
