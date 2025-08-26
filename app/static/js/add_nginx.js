$( function() {
	$(".redirectUpstream").on("click", function () {
		resetProxySettings();
		$("#tabs").tabs("option", "active", 2);
		$("#serv2").selectmenu("open");
	});
	$(".redirectProxyPass").on("click", function () {
		resetProxySettings();
		$("#tabs").tabs("option", "active", 1);
		$("#serv1").selectmenu("open");
	});
	$("#create-ssl-proxy_pass").on("click", function () {
		resetProxySettings();
		createSsl(1);
	});
	$("#serv2").on('selectmenuchange', function () {
		$('#name').focus();
	});
	$('[name=add-server-input]').click(function () {
		$("[name=add_servers]").append(add_server_nginx_var);
	});
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
	$("#scheme").on('selectmenuchange', function () {
		if ($("#scheme option:selected").val() === "http") {
			$('#hide-scheme').hide();
		} else {
			$('#hide-scheme').show();
		}
	});
	$("#compression").click(function () {
		if ($("#compression").is(':checked')) {
			$('#compression-options').show();
		} else {
			$('#compression-options').hide();
		}
	});
	$("#show_header").on("click", function () {
		$("#header_div").show();
		$("#add_header").show();
		$("#show_header").hide();
	});
	$("#add_header").click(function () {
		make_actions_for_adding_header('#header_div');
	});
	$("#show_alias").on("click", function () {
		$("#name_alias_div").show();
		$("#add_name_alias").show();
		$("#show_alias").hide();
	});
	$("#add_name_alias").click(function () {
		make_actions_for_adding_alias('#name_alias_div');
	});
	for (let section_type of ['ssl_key', 'ssl_crt']) {
		let cert_type = section_type.split('_')[1];
		$("#" + section_type).autocomplete({
			source: function (request, response) {
				let server = $("#add-proxy_pass select[name='server'] option:selected");
				if (!checkIsServerFiled("#add-proxy_pass select[name='server'] option:selected")) return false;
				$.ajax({
					url: "/add/certs/" + server.val() + "?cert_type=" + cert_type,
					success: function (data) {
						data = data.replace(/\s+/g, ' ');
						response(data.split(" "));
					}
				});
			},
			autoFocus: true,
			minLength: -1
		});
	}
	$("#proxy_pass-upstream").autocomplete({
		source: function (request, response) {
			let server = $("#add-proxy_pass select[name='server'] option:selected");
			if (!checkIsServerFiled("#add-proxy_pass select[name='server'] option:selected")) return false;
			$.ajax({
				url: "/add/get/upstreams/" + server.val(),
				success: function (data) {
					data = data.replace(/\s+/g, ' ');
					response(data.split(" "));
				}
			});
		},
		autoFocus: true,
		minLength: -1
	});
	$("#add5").on("click", function () {
		$("#tabs").tabs("option", "active", 3);
	});
});
var header_option = '<p style="border-bottom: 1px solid #ddd; padding-bottom: 10px;" id="new_header_p">\n' +
	'<select name="headers_res">' +
	'<option value="------">------</option>' +
	'<option value="add_header">add_header</option>' +
	'<option value="proxy_set_header">proxy_set_header</option>' +
	'<option value="proxy_hide_header">proxy_hide_header</option>' +
	'</select>' +
	'\t<b class="padding10">'+name_word+'</b>' +
	'\t<input name="header_name" class="form-control">' +
	'\t<b class="padding10">'+value_word+'</b>' +
	'\t<input name="header_value" class="form-control">' +
	'\t<span class="minus minus-style" id="new_header_minus" title="Delete this header"></span>' +
	'</p>'
function make_actions_for_adding_header(section_id) {
	let random_id = makeid(3);
	$(section_id).append(header_option);
	$('#new_header_minus').attr('onclick', 'deleteId(\''+random_id+'\')');
	$('#new_header_minus').attr('id', '');
	$('#new_header_p').attr('id', random_id);
	$('#new_header_minus').attr('id', '');
	$.getScript(awesome);
	$( "select" ).selectmenu();
	$('[name=headers_method]').selectmenu({width: 180});
}
var alias_option = '<p style="border-bottom: 1px solid #ddd; padding-bottom: 10px;" id="new_name_alias_p">\n' +
	'<input type="text" name="name_alias" data-help="Domain name or IP" size="" style="" placeholder="www.example.com" title="Domain name or IP" class="form-control">' +
	'\t<span class="minus minus-style" id="new_name_alias_minus" title="Delete this alias"></span>' +
	'</p>'
function make_actions_for_adding_alias(section_id) {
	let random_id = makeid(3);
	$(section_id).append(alias_option);
	$('#new_name_alias_minus').attr('onclick', 'deleteId(\''+random_id+'\')');
	$('#new_name_alias_minus').attr('id', '');
	$('#new_name_alias_p').attr('id', random_id);
	$('#new_name_alias_minus').attr('id', '');
	$.getScript(awesome);
}
function deleteId(id) {
	$('#' + id).remove();
}
function resetProxySettings() {
	$('[name=name]').val('');
	$('input:checkbox').prop("checked", false);
	$('[name=check-servers]').prop("checked", true);
	$('input:checkbox').checkboxradio("refresh");
	$('.advance-show').fadeIn();
	$('.advance').fadeOut();
	$('select').selectmenu('refresh');
	$("#path-cert-listen").attr('required', false);
	$("#path-cert-frontend").attr('required', false);
}
function addProxy(form_name, generate = false) {
	let frm = $('#'+form_name);
	let serv = '#serv1';
	let name_id = '';
	if (form_name === 'add-upstream') {
		serv = '#serv2'
		name_id = '#upstream-name'
	} else if (form_name === 'add-proxy_pass') {
		serv = '#serv1'
		name_id = '#proxy_pass'
	}
	if(!checkIsServerFiled(serv)) return false;
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	let json_data = getNginxFormData(frm, form_name);
	let section_type = form_name.split('-')[1]
	let q_generate = '';
	if (generate) {
		q_generate = '?generate=1';
	}
	$.ajax({
		url: '/add/nginx/' + $(serv).val() + '/section/' + section_type + q_generate,
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
function getNginxFormData($form, form_name) {
	let section_type = form_name.split('-')[1]
	let unindexed_array = $form.serializeArray();
	let indexed_array = {};
	indexed_array['locations'] = [];
	indexed_array['backend_servers'] = [];
	indexed_array['name_aliases'] = [];
	indexed_array['security'] = {};
	let headers = [];

	$.map(unindexed_array, function (n, i) {
		if (n['name'] === 'location') {
			let location = $('input[name="location"]').val();
			let proxy_connect_timeout = $('input[name="proxy_connect_timeout"]').val();
			let proxy_read_timeout = $('input[name="proxy_read_timeout"]').val();
			let proxy_send_timeout = $('input[name="proxy_send_timeout"]').val();
			let upstream = $('input[name="upstream"]').val();
			$('#header_div p').each(function () {
				let action = $(this).children().children('select[name="headers_res"] option:selected').val();
				let name = $(this).children('input[name="header_name"]').val();
				let value = $(this).children('input[name="header_value"]').val();
				if (action === '------') {
					return;
				}
				if (name === '') {
					return;
				}
				let header = {action, name, value};
				headers.push(header);
			});
			let location_config = {
				location,
				proxy_connect_timeout,
				proxy_read_timeout,
				proxy_send_timeout,
				headers,
				upstream
			};
			indexed_array['locations'].push(location_config)
		} else if (n['name'] === 'ssl_offloading') {
			if ($('input[name="ssl_offloading"]').is(':checked')) {
				indexed_array['ssl_offloading'] = true;
			} else {
				indexed_array['ssl_offloading'] = false;
			}
		} else if (n['name'] === 'hsts') {
			if ($('input[name="hsts"]').is(':checked')) {
				indexed_array['hsts'] = true;
			} else {
				indexed_array['hsts'] = false;
			}
		} else if (n['name'] === 'http2') {
			if ($('input[name="http2"]').is(':checked')) {
				indexed_array['http2'] = true;
			} else {
				indexed_array['http2'] = false;
			}
		} else {
			indexed_array[n['name']] = n['value'];
		}
	});
	$('#name_alias_div p').each(function () {
		let name = $(this).children("input[name='name_alias']").val();
		if (name === undefined || name === '') {
			return;
		}
		indexed_array['name_aliases'].push(name);
	});
	let hide_server_tokens = false;
	let security_headers = false;
	let hide_backend_headers = false;
	if ($('#hide_server_tokens').is(':checked')) {
		hide_server_tokens = true;
	}
	if ($('#security_headers').is(':checked')) {
		security_headers = true;
	}
	if ($('#hide_backend_headers').is(':checked')) {
		hide_backend_headers = true;
	}
	indexed_array['security'] = {
		'hide_server_tokens': hide_server_tokens,
		'security_headers': security_headers,
		'hide_backend_headers': hide_backend_headers
	};
	$('#' + form_name + ' span[name="add_servers"] p').each(function () {
		let server = $(this).children("input[name='servers']").val();
		if (server === undefined || server === '') {
			return;
		}
		let port = $(this).children("input[name='server_port']").val();
		let max_fails = $(this).children("input[name='max_fails']").val();
		let fail_timeout = $(this).children("input[name='fail_timeout']").val();
		let test_var = {server, port, max_fails, fail_timeout};
		indexed_array['backend_servers'].push(test_var);
	});
	let elementsForDelete = [
		'servers', 'server_port', 'max_fails', 'fail_timeout', 'proxy_connect_timeout', 'proxy_read_timeout', 'proxy_send_timeout',
		'headers_res', 'header_name', 'header_value', 'upstream', 'server', 'name_alias', 'hide_server_tokens', 'security_headers',
		'hide_backend_headers'
	]
	for (let element of elementsForDelete) {
		delete indexed_array[element]
	}
	return indexed_array;
}
function createSsl(TabId) {
	$('[name=port]').val('443');
	$("#tabs").tabs("option", "active", TabId);
	$("#hide-scheme").show("fast");
	$('#scheme').val('https');
	$('#ssl_offloading').prop("checked", true);
	$('input:checkbox').checkboxradio("refresh");
	$("#ssl_key").attr('required', true);
	if (TabId === 1) {
		TabId = '';
	}
	$("#serv" + TabId).selectmenu("open");
	$("#scheme").selectmenu("refresh");
	history.pushState('Add proxy pass', 'Add proxy pass', 'nginx#proxypass')
}
