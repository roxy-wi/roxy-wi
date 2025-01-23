// Translate
const translate_div = $('#translate');
const cancel_word = translate_div.attr('data-cancel');
let add_word = translate_div.attr('data-add');
const close_word = translate_div.attr('data-close');
const service_word = translate_div.attr('data-service');
const save_word = translate_div.attr('data-save');
const just_save_word = translate_div.attr('data-just_save');
const upload_and_reload = translate_div.attr('data-upload_and_reload');
const upload_and_restart = translate_div.attr('data-upload_and_restart');
const edit_word = translate_div.attr('data-edit');
const delete_word = translate_div.attr('data-delete');
const back_word = translate_div.attr('data-back');
const nice_service_name = {'keepalived': 'HA Custer', 'haproxy': 'HAProxy', 'nginx': 'NGINX', 'apache': 'Apache', 'caddy': 'Caddy'};

// JS scripts URL
const scriptPath = "/static/js"
const script = `${scriptPath}/script.js`;
const overview = `${scriptPath}/overview.js`;
const configShow = `${scriptPath}/configshow.js`;
const awesome = `${scriptPath}/fontawesome.min.js`;
const ha = `${scriptPath}/ha.js`;
const waf = `${scriptPath}/waf.js`

// csrf_token
const csrf_token = Cookies.get('csrf_access_token');

// API prefix
const api_prefix = '/api'

// Add page
const add_server_var = '<br /><input name="servers" title="Backend IP" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control second-server" style="margin: 2px 0 4px 0;">: ' +
		'<input name="server_port" required title="Backend port" size=3 placeholder="yyy" class="form-control second-server add_server_number" type="number"> ' +
		'Port check: <input name="port_check" required title="Maxconn. Default 200" size=5 value="200" class="form-control add_server_number" type="number">' +
		' maxconn: <input name="server_maxconn" required title="Maxconn. Default 200" size=5 value="200" class="form-control add_server_number" type="number">'
const add_userlist_group_var = '<p><input name="userlist-group" title="User`s group" placeholder="group_name" class="form-control"></p>'
const add_userlist_var = '<p><input name="userlist-user" title="User name" placeholder="user_name" class="form-control"> <input name="userlist-password" required title="User password. By default it insecure-password" placeholder="password" class="form-control"> <input name="userlist-user-group" title="User`s group" placeholder="user`s group" class="form-control"></p>'
const add_peer_var = '<p><input name="servers_name" required title="Peer name" size=14 placeholder="haproxyN" class="form-control">: ' +
		'<input name="servers" title="Backend IP" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control second-server">: ' +
		'<input name="server_port" required title="Backend port" size=3 placeholder="yyy" class="form-control second-server add_server_number" type="number"></p>'
