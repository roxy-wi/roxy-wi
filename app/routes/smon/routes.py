import json
from flask import render_template, request, jsonify, g
from flask_login import login_required
from datetime import datetime

from app.routes.smon import bp
from app.middleware import get_user_params
import app.modules.db.history as history_sql
import app.modules.db.smon as smon_sql
import app.modules.db.channel as channel_sql
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
import app.modules.tools.smon as smon_mod
import app.modules.tools.common as tools_common


@bp.route('/dashboard')
@login_required
@get_user_params()
def smon_main_dashboard():
    """
    Dashboard route for the smon tool.

    :return: The rendered dashboard template with the necessary parameters.
    :rtype: flask.Response
    """
    roxywi_common.check_user_group_for_flask()
    group_id = g.user_params['group_id']

    kwargs = {
        'autorefresh': 1,
        'lang': g.user_params['lang'],
        'smon': smon_sql.smon_list(group_id),
        'agents': smon_sql.get_agents(group_id),
        'group': group_id,
        'smon_status': tools_common.is_tool_active('roxy-wi-smon'),
        'user_subscription': roxywi_common.return_user_subscription(),
        'telegrams': channel_sql.get_user_telegram_by_group(group_id),
        'slacks': channel_sql.get_user_pd_by_group(group_id),
        'pds': channel_sql.get_user_slack_by_group(group_id),
        'sort': request.args.get('sort', None)
    }

    return render_template('smon/dashboard.html', **kwargs)


@bp.route('/dashboard/<int:smon_id>/<int:check_id>')
@login_required
@get_user_params()
def smon_dashboard(smon_id, check_id):
    """
    :param smon_id: The ID of the SMON (Server Monitoring) service.
    :param check_id: The ID of the check associated with the SMON service.
    :return: The rendered SMON dashboard template.

    This method is used to render the SMON dashboard template for a specific SMON service and check. It retrieves relevant data from the database and passes it to the template for rendering
    *.

    The `smon_id` parameter specifies the ID of the SMON service.
    The `check_id` parameter specifies the ID of the check associated with the SMON service.

    The method performs the following steps:
    1. Checks user group for Flask access.
    2. Retrieves the SMON object from the database using the `smon_id` and `check_id` parameters.
    3. Gets the current date and time using the `get_present_time()` function from the common module.
    4. Sets the initial value of `cert_day_diff` as 'N/A'.
    5. Tries to calculate the average response time for the SMON service using the `get_avg_resp_time` function from the SQL module. If an exception occurs, the average response time is
    * set to 0.
    6. Tries to retrieve the last response time for the SMON service and check using the `get_last_smon_res_time_by_check` function from the SQL module. If an exception occurs, the last
    * response time is set to 0.
    7. Iterates over the retrieved SMON object and checks if the SSL expiration date is not None. If it is not None, calculates the difference in days between the expiration date and the
    * present date using the `datetime.strptime()` function and assigns it to `cert_day_diff`.
    8. Constructs a dictionary (`kwargs`) containing various parameters required for rendering the template, including `autorefresh`, `lang`, `smon`, `group`, `user_subscription`, `check
    *_interval`, `uptime`, `avg_res_time`, `smon_name`, `cert_day_diff`, `check_id`, `dashboard_id`, and `last_resp_time`.
    9. Renders the SMON history template ('include/smon/smon_history.html') using the `render_template` function from Flask, passing the `kwargs` dictionary as keyword arguments.
    """
    roxywi_common.check_user_group_for_flask()
    smon = smon_sql.select_one_smon(smon_id, check_id)
    present = common.get_present_time()
    cert_day_diff = 'N/A'

    try:
        avg_res_time = round(smon_sql.get_avg_resp_time(smon_id, check_id), 2)
    except Exception:
        avg_res_time = 0
    try:
        last_resp_time = round(smon_sql.get_last_smon_res_time_by_check(smon_id, check_id), 2)
    except Exception:
        last_resp_time = 0

    for s in smon:
        if s.smon_id.ssl_expire_date is not None:
            ssl_expire_date = datetime.strptime(s.smon_id.ssl_expire_date, '%Y-%m-%d %H:%M:%S')
            cert_day_diff = (ssl_expire_date - present).days

    kwargs = {
        'autorefresh': 1,
        'lang': g.user_params['lang'],
        'smon': smon,
        'group': g.user_params['group_id'],
        'user_subscription': roxywi_common.return_user_subscription(),
        'uptime': smon_mod.check_uptime(smon_id),
        'avg_res_time': avg_res_time,
        'smon_name': smon_sql.get_smon_service_name_by_id(smon_id),
        'cert_day_diff': cert_day_diff,
        'check_id': check_id,
        'dashboard_id': smon_id,
        'last_resp_time': last_resp_time,
        'agents': smon_sql.get_agents(g.user_params['group_id'])
    }

    return render_template('include/smon/smon_history.html', **kwargs)


@bp.route('/check', methods=['POST', 'PUT', 'DELETE'])
@login_required
def smon_add():
    json_data = request.get_json()
    if request.method == "POST":
        user_group = roxywi_common.get_user_group(id=1)

        try:
            last_id = smon_mod.create_smon(json_data, user_group)
        except Exception as e:
            return str(e), 200
        return str(last_id)
    elif request.method == "PUT":
        check_id = json_data['check_id']

        if roxywi_common.check_user_group_for_flask():
            try:
                status = smon_mod.update_smon(check_id, json_data)
            except Exception as e:
                return f'{e}', 200
            else:
                return status, 201
    elif request.method == "DELETE":
        user_group = roxywi_common.get_user_group(id=1)
        check_id = json_data['check_id']

        if roxywi_common.check_user_group_for_flask():
            try:
                status = smon_mod.delete_smon(check_id, user_group)
            except Exception as e:
                return f'{e}', 200
            else:
                return status


@bp.route('/check/settings/<int:smon_id>/<int:check_type_id>')
@login_required
def check(smon_id, check_type_id):
    smon = smon_sql.select_one_smon(smon_id, check_type_id)
    settings = {}
    for s in smon:
        settings = {
            'id': s.smon_id.id,
            'name': s.smon_id.name,
            'interval': str(s.interval),
            'agent_id': str(s.agent_id),
            'enabled': s.smon_id.en,
            'status': s.smon_id.status,
            'http': s.smon_id.http,
            'desc': s.smon_id.desc,
            'tg': s.smon_id.telegram_channel_id,
            'slack': s.smon_id.slack_channel_id,
            'pd': s.smon_id.pd_channel_id,
            'check_type': s.smon_id.check_type,
            'group': s.smon_id.group,
        }
        if check_type_id in (1, 5):
            settings.setdefault('port', s.port)

        if check_type_id != 2:
            settings.setdefault('server_ip', str(s.ip))
        if check_type_id == 2:
            settings.setdefault('url', s.url)
            settings.setdefault('method', s.method)
            settings.setdefault('body', s.body)
        elif check_type_id == 4:
            settings.setdefault('packet_size', s.packet_size)
        elif check_type_id == 5:
            settings.setdefault('resolver', s.resolver)
            settings.setdefault('record_type', s.record_type)

    return jsonify(settings)


@bp.route('/check/<int:smon_id>/<int:check_type_id>')
@login_required
@get_user_params()
def get_check(smon_id, check_type_id):
    """
    Get the check for the given SMON ID and check type ID.

    Parameters:
    - smon_id (int): The ID of the SMON.
    - check_type_id (int): The ID of the check type.

    Returns:
    - flask.Response: The rendered template for the check page.
    """
    smon = smon_sql.select_one_smon(smon_id, check_type_id)
    lang = roxywi_common.get_user_lang_for_flask()
    agents = smon_sql.get_agents(g.user_params['group_id'])
    return render_template('ajax/smon/check.html', smon=smon, lang=lang, check_type_id=check_type_id, agents=agents)


@bp.route('/status-page', methods=['GET', 'POST', 'DELETE', 'PUT'])
@login_required
@get_user_params()
def status_page():
    """
       This function handles the '/status-page' route with methods GET, POST, DELETE, and PUT.
       It requires the user to be logged in and retrieves user parameters.

       :return:
          - GET method: Renders the 'smon/manage_status_page.html' template with the following keyword arguments:
              - 'lang': The language from user parameters
              - 'smon': The list of smon from sql.smon_list() using the 'group_id' from user parameters
              - 'pages': The status pages from sql.select_status_pages() using the 'group_id' from user parameters
              - 'smon_status': The status of the 'roxy-wi-smon' tool from tools_common.is_tool_active()
              - 'user_subscription': The user subscription from roxywi_common.return_user_subscription()
          - POST method: Creates a status page with the following parameters:
              - 'name': The name of the status page
              - 'slug': The slug of the status page
              - 'desc': The description of the status page
              - 'checks': The checks for the status page
          - PUT method: Edits a status page with the following parameters:
              - 'page_id': The ID of the status page
              - 'name': The updated name of the status page
              - 'slug': The updated slug of the status page
              - 'desc': The updated description of the status page
              - 'checks': The updated checks for the status page
          - DELETE method: Deletes a status page with the following parameter:
              - 'page_id': The ID of the status page

       The function returns different values based on the method used:
          - POST method: Returns the result of smon_mod.create_status_page() for creating the status page or an exception message in case of an error.
          - PUT method: Returns the result of smon_mod.edit_status_page() for editing the status page or an exception message in case of an error.
          - DELETE method: Returns 'ok' if the status page is successfully deleted or an exception message in case of an error.

       .. note::
          - The checks for the status page should not be empty. If no checks are selected, it returns an error message.
          - Any exceptions raised during the process will be returned as exception messages.
    """
    if request.method == 'GET':
        kwargs = {
            'lang': g.user_params['lang'],
            'smon': smon_sql.smon_list(g.user_params['group_id']),
            'pages': smon_sql.select_status_pages(g.user_params['group_id']),
            'smon_status': tools_common.is_tool_active('roxy-wi-smon'),
            'user_subscription': roxywi_common.return_user_subscription()
        }

        return render_template('smon/manage_status_page.html', **kwargs)
    elif request.method == 'POST':
        name = common.checkAjaxInput(request.form.get('name'))
        slug = common.checkAjaxInput(request.form.get('slug'))
        desc = common.checkAjaxInput(request.form.get('desc'))
        checks = json.loads(request.form.get('checks'))

        if not len(checks['checks']):
            return 'error: Please check Checks for Status page'

        try:
            return smon_mod.create_status_page(name, slug, desc, checks['checks'])
        except Exception as e:
            return f'{e}'
    elif request.method == 'PUT':
        page_id = int(request.form.get('page_id'))
        name = common.checkAjaxInput(request.form.get('name'))
        slug = common.checkAjaxInput(request.form.get('slug'))
        desc = common.checkAjaxInput(request.form.get('desc'))
        checks = json.loads(request.form.get('checks'))

        if not len(checks['checks']):
            return 'error: Please check Checks for Status page'

        try:
            return smon_mod.edit_status_page(page_id, name, slug, desc, checks['checks'])
        except Exception as e:
            return f'{e}'
    elif request.method == 'DELETE':
        page_id = int(request.form.get('page_id'))
        try:
            smon_sql.delete_status_page(page_id)
        except Exception as e:
            return f'{e}'
        else:
            return 'ok'


@bp.route('/status/checks/<int:page_id>')
@login_required
def get_checks(page_id):
    """
    :param page_id: The ID of the page for which to fetch the checks.
    :return: A JSON response with an array of check IDs.

    """
    returned_check = []
    try:
        checks = smon_sql.select_status_page_checks(page_id)
    except Exception as e:
        return f'error: Cannot get checks: {e}'

    for check in checks:
        returned_check.append(str(check.check_id))

    return jsonify(returned_check)


@bp.route('/status/<slug>')
def show_smon_status_page(slug):
    slug = common.checkAjaxInput(slug)

    return smon_mod.show_status_page(slug)


@bp.route('/status/avg/<int:page_id>')
def smon_history_statuses_avg(page_id):
    return smon_mod.avg_status_page_status(page_id)


@bp.route('/history')
@login_required
@get_user_params()
def smon_history():
    roxywi_common.check_user_group_for_flask()

    kwargs = {
        'lang': g.user_params['lang'],
        'smon': history_sql.alerts_history('SMON', g.user_params['group_id']),
        'smon_status': tools_common.is_tool_active('roxy-wi-smon'),
        'user_subscription': roxywi_common.return_user_subscription(),
        'action': 'smon'
    }

    return render_template('smon/history.html', **kwargs)


@bp.route('/history/host/<server_ip>')
@login_required
@get_user_params()
def smon_host_history(server_ip):
    roxywi_common.check_user_group_for_flask()

    needed_host = common.checkAjaxInput(server_ip)
    smon_status = tools_common.is_tool_active('roxy-wi-smon')
    smon = history_sql.alerts_history('SMON', g.user_params['group_id'], host=needed_host)
    user_subscription = roxywi_common.return_user_subscription()
    kwargs = {
        'lang': g.user_params['lang'],
        'smon': smon,
        'smon_status': smon_status,
        'user_subscription': user_subscription,
        'action': 'smon'
    }

    return render_template('smon/history.html', **kwargs)


@bp.route('/history/metric/<int:dashboard_id>')
@login_required
def smon_history_metric(dashboard_id):
    return jsonify(smon_mod.history_metrics(dashboard_id))


@bp.route('/history/statuses/<int:dashboard_id>')
def smon_history_statuses(dashboard_id):
    return smon_mod.history_statuses(dashboard_id)


@bp.route('/history/cur_status/<int:dashboard_id>/<int:check_id>')
@login_required
def smon_history_cur_status(dashboard_id, check_id):
    return smon_mod.history_cur_status(dashboard_id, check_id)


@bp.post('/refresh')
@login_required
def smon_show():
    sort = common.checkAjaxInput(request.form.get('sort'))
    return smon_mod.show_smon(sort)
