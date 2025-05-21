function openSection(section) {
	let section_type = section.split(' ')[0];
	let section_name = section.split(' ')[1];
	let url = '/add/haproxy/' + $('#serv').val() + '/section/' + section_type + '/' + section_name;
	clearEditSection();
	if (section === 'global' || section === 'defaults') {
		url = '/add/haproxy/' + $('#serv').val() + '/section/' + section_type;
		section_type = section;
		section_name = section;
	}
	$.ajax({
		url: url,
		contentType: "application/json; charset=utf-8",
		statusCode: {
			404: function (xhr) {
				window.open('/config/section/haproxy/' + $('#serv').val() + '/' + section, '_blank').focus();
			}
		},
		async: false,
		success: function (data) {
			$('.advance-show-button').click(function () {
				$('.advance').fadeIn();
				$('.advance-show-button').css('display', 'none');
				$('.advance-hide-button').css('display', 'block');
				return false;
			});
			$('.advance-hide-button').click(function () {
				$('.advance').fadeOut();
				$('.advance-show-button').css('display', 'block');
				$('.advance-hide-button').css('display', 'none');
				return false;
			});
			let section_id = '#add-' + section_type;
			$.getScript(awesome);
			$('#edit-' + section_type).show();
			$('#edit-' + section_type + ' caption').hide();
			$('#' + section_type + '-add-buttons').hide();
			let i = 0;
			Object.keys(data.config).forEach(function (key) {
				if ($(section_id + ' *[name="' + key + '"]').prop("tagName") === 'SELECT') {
					$(section_id + ' select[name="' + key + '"]').val(data.config[key]).change();
				} else if ($(section_id + ' *[name="' + key + '"]').prop("tagName") === 'TEXTAREA') {
					$(section_id + ' select[name="' + key + '"]').val(data.config['option']).change();
				} else {
					if ($(section_id + ' *[name="' + key + '"]').prop('type') === 'checkbox') {
						if (data.config[key]) {
							$(section_id + ' input[name="' + key + '"]').prop("checked", true);
						}
					} else {
						$(section_id + ' input[name="' + key + '"]').val(data.config[key]);
					}
				}
			});
			if (data.config.option) {
				$(section_id + ' textarea[name="option"]').val(data.config.option);
			}
			if (section_type === 'global') {
				if (data.config.daemon > 0) {
					$('#global-daemon').prop("checked", true);
				} else {
					$('#global-daemon').prop("checked", false);
				}
				if (data.config.log) {
					let logs = '';
					for (let log of data.config.log) {
						logs += log + '\n';
					}
					$(section_id + ' textarea[name="log"]').val(logs);
				}
				if (data.config.socket) {
					let sockets = '';
					for (let socket of data.config.socket) {
						sockets += socket + '\n';
					}
					$(section_id + ' textarea[name="socket"]').val(sockets);
				}
			}
			if (section_type === 'defaults') {
				if (data.config.timeout) {
					Object.keys(data.config.timeout).forEach(function (key) {
						$(section_id + ' input[name="'+key+'"]').val(data.config.timeout[key]);
					});
				}
			}
			if (section_type === 'listen' || section_type === 'frontend') {
				if (data.config.binds.length > 0) {
					for (let i = 1; i < data.config.binds.length; i++) {
						make_actions_for_adding_bind('#' + section_type + '_bind');
					}
				}
				for (let bind of data.config.binds) {
					$(section_id + ' input[name="ip"]').get(i).value = bind.ip;
					$(section_id + ' input[name="port"]').get(i).value = bind.port;
					i++;
				}
				if (data.blacklist) {
					$('#'+section_type+'_blacklist_checkbox').prop("checked", true);
					$("#" + section_type + "_blacklist-hide").show("fast");
				} else {
					$('#'+section_type+'_blacklist_checkbox').prop("checked", false);
				}
				if (data.whitelist) {
					$('#'+section_type+'_whitelist_checkbox').prop("checked", true);
					$("#" + section_type + "_whitelist-hide").show("fast");
				} else {
					$('#'+section_type+'_whitelist_checkbox').prop("checked", false);
				}
			}
			if (section_type === 'listen' || section_type === 'backend') {
				if (data.config.backend_servers) {
					if (data.config.backend_servers.length > 3) {
						for (let i = 2; i < data.config.backend_servers.length; i++) {
							$("[name=add_servers]").append(add_server_var);
						}
					}
					let serv_ports = $('.send_proxy');
					for (let i = 0; i <= serv_ports.length; i++) {
						var uniqId = makeid(3);
						$(serv_ports[i]).append('<label for="' + uniqId + '" class="send_proxy_label" title="Set send-proxy for this server" data-help="The Send-proxy parameter enforces the use of the PROXY protocol over any connection established to this server. The PROXY protocol informs the other end about the layer 3/4 addresses of the incoming connection so that it can know the client\'s address or the public address it accessed to, whatever the upper-layer protocol.">send-proxy</label><input type="checkbox" name="send_proxy" value="1" id="' + uniqId + '">');
						var uniqId = makeid(3);
						$(serv_ports[i]).append('<label for="' + uniqId + '" class="send_proxy_label" title="Set this server as backup server" data-help="When all servers in a farm are down, we want to redirect traffic to a backup server which delivers either sorry pages or a degraded mode of the application.\n' +
							'This can be done easily in HAProxy by adding the keyword backup on the server line. If multiple backup servers are configured, only the first active one is used.">backup</label><input type="checkbox" name="backup" value="1" id="' + uniqId + '">');
					}
					i = 0;
					if (data.config.backend_servers.length > 0) {
						for (let bind of data.config.backend_servers) {
							$(section_id + ' input[name="servers"]').get(i).value = bind.server;
							$(section_id + ' input[name="server_port"]').get(i).value = bind.port;
							$(section_id + ' input[name="port_check"]').get(i).value = bind.port_check;
							$(section_id + ' input[name="server_maxconn"]').get(i).value = bind.maxconn;
							if (bind.send_proxy) {
								let check_id = $(section_id + ' input[name="send_proxy"]').get(i).id;
								$('#' + check_id).prop("checked", true);
							}
							if (bind.backup) {
								let backup_id = $(section_id + ' input[name="backup"]').get(i).id;
								$('#' + backup_id).prop("checked", true);
							}
							i++;
						}
					}
				}
			}
			if (section_type === 'listen' || section_type === 'frontend' || section_type === 'backend') {
				$("#options-" + section_type + "-show").click(function () {
					if ($("#options-" + section_type + "-show").is(':checked')) {
						$("#options-" + section_type + "-show-div").show("fast");
					} else {
						$("#options-" + section_type + "-show-div").hide("fast");
					}
				});
				if (data.config.headers) {
					if (data.config.headers.length > 0) {
						i = 0;
						$("#add_" + section_type + "_header").on("click", function () {
							$("#" + section_type + "_header_div").show();
							$("#" + section_type + "_add_header").show();
							$("#add_" + section_type + "_header").hide();
						});
						$('#add_' + section_type + '_header').trigger('click');
						for (let header of data.config.headers) {
							make_actions_for_adding_header('#' + section_type + '_header_div')
							let headers_res_id = $(section_id + ' select[name="headers_res"]').get(i).id;
							$('#' + headers_res_id).val(header.path).change();
							let headers_method_id = $(section_id + ' select[name="headers_method"]').get(i).id;
							$('#' + headers_method_id).val(header.method).change();
							$(section_id + ' input[name="header_name"]').get(i).value = header.name;
							$(section_id + ' input[name="header_value"]').get(i).value = header.value;
							i++;
						}
					}
				}
				if (data.config.option) {
					$("#options-" + section_type + "-show").trigger('click');
				}
				if (data.config.acls) {
					if (data.config.acls.length > 0) {
						i = 0;
						$("#add_" + section_type + "_acl").on("click", function () {
							$("#" + section_type + "_acl").show();
							$("#" + section_type + "_add_acl").show();
							$("#add_" + section_type + "_acl").hide();
						});
						$("#add_" + section_type + "_acl").trigger('click');
						for (let acl of data.config.acls) {
							make_actions_for_adding_acl_rule('#' + section_type + '_acl');
							let acl_if_id = $(section_id + ' select[name="acl_if"]').get(i).id;
							$('#' + acl_if_id).val(acl.acl_if).change();
							let acl_then_id = $(section_id + ' select[name="acl_then"]').get(i).id;
							$('#' + acl_then_id).val(acl.acl_then).change();
							$(section_id + ' input[name="acl_value"]').get(i).value = acl.acl_value;
							$(section_id + ' input[name="acl_then_value"]').get(i).value = acl.acl_then_value;
							i++;
						}
					}
				}
			}
			if (section_type === 'userlist') {
				if (data.config.userlist_groups.length > 0) {
					i = 0;
					for (let c of data.config.userlist_groups) {
						$(section_id + ' input[name="userlist-group"]').get(i).value = c;
						$('#userlist-groups').append(add_userlist_group_var);
						i++;
					}
				}
				if (data.config.userlist_users.length > 0) {
					i = 0;
					for (let c of data.config.userlist_users) {
						$(section_id + ' input[name="userlist-user"]').get(i).value = c.user;
						$(section_id + ' input[name="userlist-password"]').get(i).value = c.password;
						$(section_id + ' input[name="userlist-user-group"]').get(i).value = c.group;
						$('#userlist-users').append(add_userlist_var);
						i++;
					}
				}
			}
			if (section_type === 'peers') {
				$('[name=add-peer-input]').click(function () {
					$("[name=add_peers]").append(add_peer_var);
				});
				if (data.config.peers.length > 0) {
					i = 0;
					for (let c of data.config.peers) {
						$(section_id + ' input[name="servers_name"]').get(i).value = c.name;
						$(section_id + ' input[name="servers"]').get(i).value = c.ip;
						$(section_id + ' input[name="server_port"]').get(i).value = c.port;
						i++;
						if (i > 1) {
							$("[name=add_peers]").append(add_peer_var);
						}
					}
				}
			}
			$("select").selectmenu();
			$("select").selectmenu('refresh');
			$("input[type=checkbox]").checkboxradio();
			$("input[type=checkbox]").checkboxradio('refresh');
			$(section_id + ' select[name="server"]').val(data.server_id).change();
			$(section_id + ' select[name="server"]').selectmenu('disable').parent().parent().hide();
			$(section_id + ' input[name="name"]').prop("readonly", true).parent().parent().hide();
			let buttons = [{
					text: edit_word,
					click: function () {
						editProxy('add-' + section_type, $(this));
					}
				}, {
					text: delete_word,
					click: function () {
						confirmDeleteSection(section_type, section_name, $('#serv').val(), $(this));
					}
				}, {
					text: cancel_word,
					click: function () {
						$(this).dialog("close");
						$('#edit-' + section_type).hide();
					}
				}]
			if (section_type === 'defaults' || section_type === 'global') {
				buttons = [{
					text: edit_word,
					click: function () {
						editProxy('add-' + section_type, $(this));
					}
				}, {
					text: cancel_word,
					click: function () {
						$(this).dialog("close");
						$('#edit-' + section_type).hide();
					}
				}]
			}
			$("#edit-section").dialog({
				resizable: false,
				height: "auto",
				width: 1100,
				modal: true,
				title: edit_word,
				close: function () {
					$('#edit-' + section_type).hide();
				},
				buttons: buttons
			});
		}
	});
}
function delete_section(section_type, section_name, server_id, service) {
	$.ajax({
		url: '/add/' + service + '/' + server_id + '/section/' + section_type + '/' + section_name,
		contentType: "application/json; charset=utf-8",
		method: "DELETE",
		statusCode: {
			204: function (xhr) {
				showConfig();
			},
			404: function (xhr) {
				showConfig();
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === "failed") {
					toastr.error(data.error);
				}
			}
		}
	})
}
function clearEditSection() {
	$('#edit-section').empty();
	$.ajax({
		url: "/add/haproxy/get_section_html",
        method: "GET",
		async: false,
        success: function(data) {
            $('#edit-section').html(data);
			$.getScript('/static/js/add.js');
        },
	})
}
function addProxy(form_name, generate=false) {
	let frm = $('#'+form_name);
	let serv = '';
	let name_id = '';
	if (form_name === 'add-listen') {
		serv = '#serv'
		name_id = '#listener'
	} else if (form_name === 'add-frontend') {
		serv = '#serv2'
		name_id = '#new_frontend'
	} else if (form_name === 'add-backend') {
		serv = '#serv3'
		name_id = '#new_backend'
	} else if (form_name === 'add-userlist') {
		serv = '#userlist_serv'
		name_id = '#new_userlist'
	} else {
		serv = '#peers_serv'
		name_id = '#peers-name'
	}
	if(!checkIsServerFiled(serv)) return false;
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	let json_data = getFormData(frm, form_name);
	let section_type = form_name.split('-')[1]
	let q_generate = '';
	if (generate) {
		q_generate = '?generate=1';
	}
	$.ajax({
		url: '/add/haproxy/' + $(serv).val() + '/section/' + section_type + q_generate,
		data: JSON.stringify(json_data),
		type: frm.attr('method'),
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error)
			} else if (data === '') {
				toastr.clear();
				toastr.error('error: Something went wrong. Check configuration');
			} else {
				if (generate) {
					$('#dialog-confirm-body').text(data.data);
					let generated_title = translate_div.attr('data-generated_config');
					$("#dialog-confirm-cert").dialog({
						resizable: false,
						height: "auto",
						width: 650,
						modal: true,
						title: generated_title,
						buttons: {
							Ok: function () {
								$(this).dialog("close");
							}
						}
					});
				} else {
					toastr.clear();
					data.data = data.data.replace(/\n/g, "<br>");
					if (returnNiceCheckingConfig(data.data) === 0) {
						toastr.info('Section has been added. Do not forget to restart the server');
						resetProxySettings();
					}
				}
			}
		}
	});
}
function editProxy(form_name, dialog_id, generate=false) {
	let frm = $('#'+form_name);
	let name_id = '#' +form_name + ' input[name="name"]';
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	let json_data = getFormData(frm, form_name);
	let section_type = form_name.split('-')[1]
	let url = '/add/haproxy/' + $('#serv').val() + '/section/' + section_type + '/' + $(name_id).val();
	if (section_type === 'defaults' || section_type === 'global') {
		url = '/add/haproxy/' + $('#serv').val() + '/section/' + section_type;
	}
	$.ajax({
		url: url,
		data: JSON.stringify(json_data),
		type: 'PUT',
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error)
			} else if (data === '') {
				toastr.clear();
				toastr.error('error: Something went wrong. Check configuration');
			} else {
				toastr.clear();
				data.data = data.data.replace(/\n/g, "<br>");
				if (returnNiceCheckingConfig(data.data) === 0) {
					toastr.info('Section has been updated. Do not forget to restart the server');
					$('#edit-section').remove();
					showConfig();
					$(dialog_id).dialog( "close" );
				}
			}
		}
	});
}
function getFormData($form, form_name) {
	let section_type = form_name.split('-')[1]
	let unindexed_array = $form.serializeArray();
	let indexed_array = {};
	indexed_array['acls'] = [];
	indexed_array['binds'] = [];
	indexed_array['headers'] = [];
	indexed_array['backend_servers'] = [];
	indexed_array['type'] = section_type;
	indexed_array['userlist_users'] = [];
	indexed_array['userlist_groups'] = [];
	indexed_array['peers'] = [];
	indexed_array['daemon'] = 0;

	$.map(unindexed_array, function (n, i) {
		if (n['name'] === 'cookie') {
			if ($('input[name="cookie"]').is(':checked')) {
				let name = $('input[name="cookie_name"]').val();
				let domain = $('input[name="cookie_domain"]').val();
				let dynamic = $('input[name="dynamic"]').val();
				let dynamic_key = $('input[name="dynamic-cookie-key"]').val();
				let nocache = $('input[name="nocache"]').val();
				let postonly = $('input[name="postonly"]').val();
				let rewrite = $('select[name="rewrite"] option:selected').val();
				let prefix = $('input[name="prefix"]').val();
				indexed_array['cookie'] = {name, domain, dynamic, dynamic_key, nocache, postonly, rewrite, prefix}
			}
		} else if (n['name'] === 'whitelist_checkbox') {
			if ($('input[name="whitelist_checkbox"]').is(':checked')) {
				indexed_array['whitelist'] = $('input[name="whitelist"]').val();
			}
		} else if (n['name'] === 'ssl') {
			if ($('input[name="ssl"]').is(':checked')) {
				let cert = $('input[name="cert"]').val();
				let ssl_check_backend = true;
				if ($('input[name="ssl-check"]').is(':checked')) {
					ssl_check_backend = 0;
				} else {
					ssl_check_backend = true;
				}
				indexed_array['ssl'] = {cert, ssl_check_backend};
			}
		} else if (n['name'] === 'health_check') {
			let check = n['value'];
			if (check === undefined || check === '' || check === '-------') {
				return;
			}
			let path = $('input[name="checks_http_path"]').val();
			let domain = $('input[name="checks_http_domain"]').val();
			indexed_array['health_check'] = {check, path, domain}
		} else if (n['name'] === 'blacklist_checkbox') {
			if ($('input[name="blacklist_checkbox"]').is(':checked')) {
				indexed_array['blacklist'] = $('input[name="blacklist"]').val();
			}
		} else if (n['name'] === 'ssl_offloading') {
			if ($('input[name="ssl_offloading"]').is(':checked')) {
				indexed_array['ssl_offloading'] = true;
			}
		} else if (n['name'] === 'forward_for') {
			if ($('input[name="forward_for"]').is(':checked')) {
				indexed_array['forward_for'] = true;
			}
		} else if (n['name'] === 'redispatch') {
			if ($('input[name="redispatch"]').is(':checked')) {
				indexed_array['redispatch'] = true;
			}
		} else if (n['name'] === 'slow_attack') {
			if ($('input[name="slow_attack"]').is(':checked')) {
				indexed_array['slow_attack'] = true;
			}
		} else if (n['name'] === 'ddos') {
			if ($('input[name="ddos"]').is(':checked')) {
				indexed_array['ddos'] = true;
			}
		} else if (n['name'] === 'antibot') {
			if ($('input[name="antibot"]').is(':checked')) {
				indexed_array['antibot'] = true;
			}
		} else if (n['name'] === 'cache') {
			if ($('input[name="cache"]').is(':checked')) {
				indexed_array['cache'] = true;
			}
		} else if (n['name'] === 'circuit_breaking') {
			if ($('input[name="circuit_breaking"]').is(':checked')) {
				let observe = $('select[name="circuit_breaking_observe"] option:selected').val();
				let error_limit = $('input[name="circuit_breaking_error_limit"]').val();
				let on_error = $('select[name="circuit_breaking_on_error"] option:selected').val();
				indexed_array['circuit_breaking'] = {observe, error_limit, on_error};
			}
		} else if (n['name'] === 'check-servers') {
			if ($('input[name="check-servers"]').is(':checked')) {
				let check_enabled = true;
				let inter = $('select[name="inter"] option:selected').val();
				let rise = $('select[name="rise"] option:selected').val();
				let fall = $('select[name="fall"] option:selected').val();
				indexed_array['servers_check'] = {check_enabled, inter, rise, fall};
			} else {
				let check_enabled = 0;
				indexed_array['servers_check'] = {check_enabled}
			}
		} else if (n['name'] === 'template') {
			if ($('input[name="template"]').is(':checked')) {
				let prefix = $('input[name="template-prefix"]').val();
				let count = $('input[name="template-number"]').val();
				let servers = $('input[name="servers"]').val();
				let port = $('input[name="server_port"]').val();
				indexed_array['servers_template'] = {prefix, count, servers, port};
			}
		} else if (n['name'] === 'log' && section_type === 'global') {
			indexed_array['log'] = [];
			for (let l of n['value'].split('\r\n')) {
				if (l != '') {
					indexed_array['log'].push(l);
				}
			}
		} else if (n['name'] === 'socket') {
			indexed_array['socket'] = [];
			for (let l of n['value'].split('\r\n')) {
				if (l != '') {
					indexed_array['socket'].push(l);
				}
			}
		} else if (n['name'] === 'daemon') {
			if ($('input[name="daemon"]').is(':checked')) {
				indexed_array['daemon'] = true;
			}
		} else {
			indexed_array[n['name']] = n['value'];
		}
	});
	$('#' +section_type+ '_acl p').each(function () {
		let acl_if = $(this).children().children("select[name='acl_if'] option:selected").val();
		if (acl_if === undefined || acl_if === '' || acl_if === "Select if") {
			return;
		}
		let acl_value = $(this).children("input[name='acl_value']").val();
		let acl_then = $(this).children().children("select[name='acl_then'] option:selected").val();
		let acl_then_value = $(this).children("input[name='acl_then_value']").val();
		indexed_array['acls'].push({acl_if, acl_value, acl_then, acl_then_value});
	});
	$('#' +section_type+ '_bind p').each(function () {
		let ip = $(this).children("input[name='ip']").val();
		let port = $(this).children("input[name='port']").val();
		if (port === undefined || port === '') {
			return;
		}
		indexed_array['binds'].push({ip, port});
	});
	$('#' +section_type+ '_header_div p').each(function () {
		let path = $(this).children().children("select[name='headers_res'] option:selected").val();
		let method = $(this).children().children("select[name='headers_method'] option:selected").val();
		let name = $(this).children("input[name='header_name']").val();
		let value = $(this).children("input[name='header_value']").val();
		if (path === undefined || path === '' || path === '------') {
			return;
		}
		if (name === undefined || name === '') {
			return;
		}
		indexed_array['headers'].push({path, method, name, value});
	});
	$('#userlist-groups p').each(function (){
		let group = $(this).children("input[name='userlist-group']").val();
		if (group === undefined || group === '') {
			return;
		}
		indexed_array['userlist_groups'].push(group);
	});
	$('#userlist-users p').each(function (){
		let user = $(this).children("input[name='userlist-user']").val();
		let password = $(this).children("input[name='userlist-password']").val();
		let group = $(this).children("input[name='userlist-user-group']").val();
		if (user === undefined || user === '' || password === undefined || password === '') {
			return;
		}
		indexed_array['userlist_users'].push({user, password, group});
	});
	$('#add_peers p').each(function (){
		let name = $(this).children("input[name='servers_name']").val();
		let ip = $(this).children("input[name='servers']").val();
		let port = $(this).children("input[name='server_port']").val();
		if (name === undefined || name === '' || ip === undefined || ip === '' || port === undefined || port === '') {
			return;
		}
		indexed_array['peers'].push({name, ip, port});
	});
	$('#'+form_name+' span[name="add_servers"] p').each(function (){
		let server = $(this).children("input[name='servers']").val();
		if (server === undefined || server === '') {
			return;
		}
		let port = $(this).children("input[name='server_port']").val();
		let port_check = $(this).children("input[name='port_check']").val();
		let maxconn = $(this).children("input[name='server_maxconn']").val();
		let send_proxy = 0;
		let backup = 0;
		if ($(this).children().children('input[name="send_proxy"]').is(':checked')) {
			send_proxy = true;
		}
		if ($(this).children().children('input[name="backup"]').is(':checked')) {
			backup = true;
		}
		let test_var = {server, port, port_check, maxconn, send_proxy, backup};
		indexed_array['backend_servers'].push(test_var);
	});
	if (section_type === 'defaults') {
		indexed_array['timeout'] = {};
		$("input[id^='defaults-timeout']").each(function (i, el) {
			indexed_array['timeout'][el.name] = el.value;

		})
	}
	let elementsForDelete = ['acl_if', 'acl_value', 'acl_then', 'acl_then_value', 'servers', 'port', 'port_check',
		'backup', 'send_proxy', 'server_port', 'ip', 'headers_method', 'headers_res', 'header_name', 'header_value', 'server_maxconn',
		'options', 'options1', 'options2', 'cookie_domain', 'cookie_name', 'dynamic', 'dynamic-cookie-key', 'nocache', 'postonly',
		'rewrite', 'prefix', 'saved-options', 'blacklist_checkbox', 'whitelist_checkbox', 'circuit_breaking_error_limit',
		'circuit_breaking_observe', 'circuit_breaking_on_error', 'check-servers', 'checks_http_domain', 'checks_http_path',
		'options-listen-show', 'cert', 'ssl-check', 'template', 'template-number', 'fall', 'inner', 'rise',  'template-prefix',
		'saved-options1', 'userlist-group', 'userlist-password', 'userlist-user', 'userlist-user-group', 'servers_name',
		'servers', 'server_port', 'serv', 'check', 'client', 'connect', 'queue', 'server', 'http_keep_alive', 'http_request']
	for (let element of elementsForDelete) {
		delete indexed_array[element]
	}
	return indexed_array;
}
function confirmDeleteSection(section_type, section_name, serv_val, dialog_id, service='haproxy') {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + section_name + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				delete_section(section_type, section_name, serv_val, service);
				dialog_id.dialog("close");
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function openNginxSection(section) {
	let parts = section.split('_');
	let section_type = parts[0];
	let section_name = parts.slice(1).join('_');
	if (section_type === 'proxy-pass') {
		section_type = 'proxy_pass';
	}
	let url = '/add/nginx/' + $('#serv').val() + '/section/' + section_type + '/' + section_name;
	clearEditNginxSection();
	$.ajax({
		url: url,
		contentType: "application/json; charset=utf-8",
		statusCode: {
			404: function (xhr) {
				window.open('/config/nginx/' + $('#serv').val() + '/edit/' + $('#config_file_name').val(), '_self').focus();
			}
		},
		async: false,
		success: function (data) {
			$('.advance-show-button').click(function () {
				$('.advance').fadeIn();
				$('.advance-show-button').css('display', 'none');
				$('.advance-hide-button').css('display', 'block');
				return false;
			});
			$('.advance-hide-button').click(function () {
				$('.advance').fadeOut();
				$('.advance-show-button').css('display', 'block');
				$('.advance-hide-button').css('display', 'none');
				return false;
			});
			let section_id = '#add-' + section_type;
			$.getScript(awesome);
			$('#edit-' + section_type).show();
			$('#edit-' + section_type + ' caption').hide();
			$('#' + section_type + '-add-buttons').hide();
			let i = 0;
			Object.keys(data.config).forEach(function (key) {
				if ($(section_id + ' *[name="' + key + '"]').prop("tagName") === 'SELECT') {
					$(section_id + ' select[name="' + key + '"]').val(data.config[key]).change();
				} else if ($(section_id + ' *[name="' + key + '"]').prop("tagName") === 'TEXTAREA') {
					$(section_id + ' select[name="' + key + '"]').val(data.config['option']).change();
				} else {
					if ($(section_id + ' *[name="' + key + '"]').prop('type') === 'checkbox') {
						if (data.config[key]) {
							$(section_id + ' input[name="' + key + '"]').prop("checked", true);
						}
					} else {
						$(section_id + ' input[name="' + key + '"]').val(data.config[key]);
					}
				}
			});
			if (section_type === 'upstream') {
				if (data.config.backend_servers) {
					if (data.config.backend_servers.length > 3) {
						for (let i = 2; i < data.config.backend_servers.length; i++) {
							$("[name=add_servers]").append(add_server_nginx_var);
						}
					}
					i = 0;
					if (data.config.backend_servers.length > 0) {
						for (let bind of data.config.backend_servers) {
							$(section_id + ' input[name="servers"]').get(i).value = bind.server;
							$(section_id + ' input[name="server_port"]').get(i).value = bind.port;
							$(section_id + ' input[name="max_fails"]').get(i).value = bind.max_fails;
							$(section_id + ' input[name="fail_timeout"]').get(i).value = bind.fail_timeout;
							i++;
						}
					}
				}
			}
			if (section_type === 'proxy_pass') {
				for (let location of data.locations) {
					if (location.headers) {
						if (location.length > 0) {
							i = 0;
							$("#add_header").on("click", function () {
								$("#header_div").show();
								$("#add_header").show();
								$("#add_header").hide();
							});
							$('#add_header').trigger('click');
							for (let header of data.config.headers) {
								make_actions_for_adding_header('#header_div')
								let headers_res_id = $(section_id + ' select[name="headers_res"]').get(i).id;
								$('#' + headers_res_id).val(header.path).change();
								$(section_id + ' input[name="header_name"]').get(i).value = header.name;
								$(section_id + ' input[name="header_value"]').get(i).value = header.value;
								i++;
							}
						}
					}
					$('#proxy_connect_timeout').val(location.proxy_connect_timeout);
					$('#proxy_read_timeout').val(location.proxy_read_timeout);
					$('#proxy_send_timeout').val(location.proxy_send_timeout);
					$('#proxy_pass-upstream').val(location.upstream);
				}
				if (data.compression) {
					$('#compression').prop("checked", true);
					$("#compression-options").show("fast");
					$('#compression_types').val(data.compression_types);
					$('#compression_min_length').val(data.compression_min_length);
					$('#compression_level').val(data.compression_level);
				} else {
					$('#compression').prop("checked", false);
					$("#compression-options").hide("fast");
				}
				if (data.scheme === 'https') {
					$('#scheme').val('https');
					$('#hide-scheme').show();
					$("#scheme").selectmenu();
					$("#scheme").selectmenu('refresh');
				}
			}
			$(section_id + ' select[name="server"]').selectmenu();
			$(section_id + ' select[name="server"]').selectmenu('refresh');
			$("input[type=checkbox]").checkboxradio();
			$("input[type=checkbox]").checkboxradio('refresh');
			$(section_id + ' select[name="server"]').val(data.server_id).change();
			$(section_id + ' select[name="server"]').selectmenu('disable').parent().parent().hide();
			$(section_id + ' input[name="name"]').prop("readonly", true).parent().parent().hide();
			let buttons = [{
				text: edit_word,
				click: function () {
					editNginxProxy('add-' + section_type, $(this));
				}
			}, {
				text: delete_word,
				click: function () {
					confirmDeleteSection(section_type, section_name, $('#serv').val(), $(this), 'nginx');
				}
			}, {
				text: cancel_word,
				click: function () {
					$(this).dialog("close");
					$('#edit-' + section_type).hide();
				}
			}]
			$("#edit-section").dialog({
				resizable: false,
				height: "auto",
				width: 1100,
				modal: true,
				title: edit_word,
				close: function () {
					$('#edit-' + section_type).hide();
				},
				buttons: buttons
			});
		}
	});
}
function clearEditNginxSection() {
	$('#edit-section').empty();
	$.ajax({
		url: "/add/nginx/get_section_html",
        method: "GET",
		async: false,
        success: function(data) {
            $('#edit-section').html(data);
			$.getScript('/static/js/add_nginx.js');
        },
	})
}
function editNginxProxy(form_name, dialog_id, generate=false) {
	let frm = $('#'+form_name);
	let name_id = '#' +form_name + ' input[name="name"]';
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	let json_data = getNginxFormData(frm, form_name);
	let section_type = form_name.split('-')[1]
	let url = '/add/nginx/' + $('#serv').val() + '/section/' + section_type + '/' + $(name_id).val();
	$.ajax({
		url: url,
		data: JSON.stringify(json_data),
		type: 'PUT',
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error)
			} else if (data === '') {
				toastr.clear();
				toastr.error('error: Something went wrong. Check configuration');
			} else {
				toastr.clear();
				data.data = data.data.replace(/\n/g, "<br>");
				if (returnNiceCheckingConfig(data.data) === 0) {
					toastr.info('Section has been updated. Do not forget to restart the server');
					showConfig();
					$('#edit-section').remove();
					$(dialog_id).dialog( "close" );
				}
			}
		}
	});
}
