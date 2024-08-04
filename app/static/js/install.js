let nice_names = {
	'haproxy': 'HAProxy',
	'nginx': 'NGINX',
	'apache': 'Apache',
	'node': 'Node',
	'keepalived': 'Keepalived'
};
$( function() {
	$('#install').click(function () {
		installService('haproxy')
	});
	$('#nginx_install').click(function () {
		installService('nginx');
	});
	$('#apache_install').click(function () {
		installService('apache');
	});
	$('#grafana_install').click(function () {
		$("#ajaxmon").html('');
		$("#ajaxmon").html(wait_mess);
		$.ajax({
			url: "/install/grafana",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				$("#ajaxmon").html('');
				if (data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1' || data.indexOf('ERROR') != '-1') {
					toastr.clear();
					let p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1') {
					toastr.clear();
					toastr.success(data);
				} else if (data.indexOf('Info') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		});
	});
	$('#haproxy_exp_install').click(function () {
		installExporter('haproxy');
	});
	$('#nginx_exp_install').click(function () {
		installExporter('nginx');
	});
	$('#apache_exp_install').click(function () {
		installExporter('apache');
	});
	$('#keepalived_exp_install').click(function () {
		installExporter('keepalived');
	});
	$('#node_exp_install').click(function () {
		installExporter('node');
	});
	$("#haproxyaddserv").on('selectmenuchange', function () {
		showServiceVersion('haproxy');
	});
	$("#nginxaddserv").on('selectmenuchange', function () {
		showServiceVersion('nginx');
	});
	$("#apacheaddserv").on('selectmenuchange', function () {
		showServiceVersion('apache');
	});
	$("#haproxy_exp_addserv").on('selectmenuchange', function () {
		showExporterVersion('haproxy');
	});
	$("#nginx_exp_addserv").on('selectmenuchange', function () {
		showExporterVersion('nginx');
	});
	$("#apache_exp_addserv").on('selectmenuchange', function () {
		showExporterVersion('apache');
	});
	$("#keepalived_exp_addserv").on('selectmenuchange', function () {
		showExporterVersion('keepalived');
	});
	$("#node_exp_addserv").on('selectmenuchange', function () {
		showExporterVersion('node');
	});
	$("#geoipserv").on('selectmenuchange', function () {
		if ($('#geoip_service option:selected').val() != '------') {
			checkGeoipInstallation();
		}
	});
	$("#geoip_service").on('selectmenuchange', function () {
		if ($('#geoipserv option:selected').val() != '------') {
			checkGeoipInstallation();
		}
	});
	$("#geoip_install").click(function () {
		let updating_geoip = 0;
		if ($('#updating_geoip').is(':checked')) {
			updating_geoip = '1';
		}
		$("#ajax-geoip").html(wait_mess);
		let service = $('#geoip_service option:selected').val();
		let jsonData = {
			"server_ip": $('#geoipserv option:selected').val(),
			"service": service,
			"update": updating_geoip
		}
		$.ajax({
			url: "/install/geoip",
			data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			type: "POST",
			success: function (data) {
				$("#ajax-geoip").html('');
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					parseAnsibleJsonOutput(data, service + ' GeoIP', '#geoip_service');
					$("#geoip_service").trigger("selectmenuchange");
				}
			}
		});
	});
});
function checkGeoipInstallation() {
	$.ajax({
		url: "/install/geoip/" + $('#geoip_service option:selected').val() + "/" + $('#geoipserv option:selected').val(),
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('No such file or directory') != '-1' || data.indexOf('cannot access') != '-1') {
				$('#cur_geoip').html('<b style="color: var(--red-color)">GeoIPLite is not installed</b>');
				$('#geoip_install').show();
			} else {
				$('#cur_geoip').html('<b style="color: var(--green-color)">GeoIPLite is installed<b>');
				$('#geoip_install').hide();
			}
		}
	});
}
function installService(service) {
	$("#ajax").html('')
	let syn_flood = 0;
	let docker = 0;
	let select_id = '#' + service + 'addserv';
	if ($('#' + service + '_syn_flood').is(':checked')) {
		syn_flood = '1';
	}
	if ($('#' + service + '_docker').is(':checked')) {
		docker = '1';
	}
	if ($(select_id).val() === '------' || $(select_id).val() === null) {
		let select_server = translate_div.attr('data-select_server');
		toastr.warning(select_server);
		return false
	}
	let jsonData = {};
	let server = {
		"ip": $(select_id).val(),
        "master": '0',
        "name": $(select_id + ' option:selected').text(),
	}
	if (service === 'haproxy') {
		server['version'] = $('#hapver option:selected').val();
	}
	jsonData['servers'] = {}
	jsonData['services'] = {};
	jsonData['services'][service] = {};
	jsonData['syn_flood'] = syn_flood;
	jsonData['servers'] = [];
	jsonData['servers'].push(server);
	jsonData['services'][service]['enabled'] = 1;
	jsonData['services'][service]['docker'] = docker;
	$("#ajax").html(wait_mess);
	$.ajax({
		url: "/install/" + service + "/" + $(select_id).val(),
		500: function () {
			showErrorStatus(nice_names[service], $(select_id + ' option:selected').text());
		},
		504: function () {
			showErrorStatus(nice_names[service], $(select_id + ' option:selected').text());
		},
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "POST",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				parseAnsibleJsonOutput(data, nice_names[service], select_id);
				$(select_id).trigger("selectmenuchange");
				$("#ajax").empty();
			}
		}
	});
}
function installExporter(exporter) {
	$("#ajaxmon").html('');
	$("#ajaxmon").html(wait_mess);
	let exporter_id = '#' + exporter + '_exp_addserv';
	let ext_prom = 0;
	let nice_exporter_name = nice_names[exporter] + ' exporter';
	if ($('#' + exporter + '_ext_prom').is(':checked')) {
		ext_prom = '1';
	}
	let jsonData = {
		"server_ip": $(exporter_id).val(),
		"exporter_v": $('#' + exporter + 'expver').val(),
		"ext_prom": ext_prom,
	}
	$("#ajax").html(wait_mess);
	$.ajax({
		url: "/install/exporter/" + exporter,
		500: function () {
			showErrorStatus(nice_exporter_name, $(exporter_id + ' option:selected').text());
		},
		504: function () {
			showErrorStatus(nice_exporter_name, $(exporter_id + ' option:selected').text());
		},
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "POST",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				parseAnsibleJsonOutput(data, nice_names[service], exporter_id);
				$(exporter_id).trigger("selectmenuchange");
				$("#ajax").empty();
			}
		}
	});
}
function showExporterVersion(exporter) {
	$.ajax({
		url: "/install/exporter/" + exporter + "/version/" + $('#' + exporter + '_exp_addserv option:selected').val(),
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('error:') != '-1') {
				toastr.clear();
				toastr.error(data);
			} else if (data == 'no' || data.indexOf('command') != '-1' || data.indexOf('_exporter:') != '-1' || data == '') {
				$('#cur_' + exporter + '_exp_ver').text(nice_names[exporter] + ' exporter has not been installed');
			} else {
				$('#cur_' + exporter + '_exp_ver').text(data);
			}
		}
	});
}
function showServiceVersion(service) {
	let install_div = $('#' + service + '_install');
	let ver_div = $('#cur_' + service + '_ver');
	$.ajax({
		url: "/service/" + service + "/" + $('#' + service + 'addserv option:selected').val() + "/status",
		statusCode: {
			404: function (xhr) {
				ver_div.text(service + ' has not installed');
				install_div.text('Install');
				install_div.attr('title', 'Install');
			}
		},
		success: function (data) {
			if (data.status === 'failed') {
				ver_div.text(service + ' has not installed');
				install_div.text('Install');
				install_div.attr('title', 'Install');
			} else {
				ver_div.text(data.Version);
				ver_div.css('font-weight', 'bold');
				install_div.text('Update');
				install_div.attr('title', 'Update');
			}
		}
	});
}
function showErrorStatus(service_name, server) {
	let something_wrong = translate_div.attr('data-something_wrong');
	toastr.error(something_wrong + ' ' + service_name + ' ' + server);
}
function parseAnsibleJsonOutput(output, service_name, select_id) {
	let was_installed = translate_div.attr('data-was_installed');
	let server_name = '';
	for (let k in output['ok']) {
		if (select_id) {
			server_name = $(select_id + ' option[value="'+k+'"]').text();
		}
		toastr.success(service_name + ' ' + was_installed +' ' + server_name);
	}
	for (let k in output['failures']) {
		if (select_id) {
			server_name = $(select_id + ' option[value="'+k+'"]').text();
		}
		showErrorStatus(service_name, server_name);
	}
	for (let k in output['dark']) {
		if (select_id) {
			server_name = $(select_id + ' option[value="'+k+'"]').text();
		}
		showErrorStatus(service_name, server_name);
	}
}
