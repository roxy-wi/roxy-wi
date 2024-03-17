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
            url: "/app/install/grafana",
            // data: {
            // 	token: $('#token').val()
            // 	},
            // type: "POST",
            success: function (data) {
                data = data.replace(/\s+/g, ' ');
                $("#ajaxmon").html('');
                if (data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1' || data.indexOf('ERROR') != '-1') {
                    toastr.clear();
                    var p_err = show_pretty_ansible_error(data);
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
    	$( "#geoipserv" ).on('selectmenuchange',function() {
		if($('#geoip_service option:selected').val() != '------') {
			checkGeoipInstallation();
		}
	});
	$( "#geoip_service" ).on('selectmenuchange',function() {
		if($('#geoipserv option:selected').val() != '------') {
			checkGeoipInstallation();
		}
	});
	$( "#geoip_install" ).click(function() {
		var updating_geoip = 0;
		if ($('#updating_geoip').is(':checked')) {
			updating_geoip = '1';
		}
		$("#ajax-geoip").html(wait_mess);
		$.ajax({
			url: "/app/install/geoip",
			data: {
				server_ip: $('#geoipserv option:selected').val(),
				service: $('#geoip_service option:selected').val(),
				update: updating_geoip,
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/^\s+|\s+$/g, '');
				$("#ajax-geoip").html('')
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1') {
					toastr.clear();
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success:') != '-1') {
					toastr.clear();
					toastr.success(data);
					$("#geoip_service").trigger("selectmenuchange");
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
});
function checkGeoipInstallation() {
	$.ajax( {
		url: "/app/install/geoip/" + $('#geoip_service option:selected').val() + "/" + $('#geoipserv option:selected').val(),
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
		success: function( data ) {
			data = data.replace(/^\s+|\s+$/g,'');
			if(data.indexOf('No such file or directory') != '-1' || data.indexOf('cannot access') != '-1') {
				$('#cur_geoip').html('<b style="color: var(--red-color)">GeoIPLite is not installed</b>');
				$('#geoip_install').show();
			} else {
				$('#cur_geoip').html('<b style="color: var(--green-color)">GeoIPLite is installed<b>');
				$('#geoip_install').hide();
			}
		}
	} );
}
function installService(service) {
	$("#ajax").html('')
	var syn_flood = 0;
	var docker = 0;
	var select_id = '#' + service + 'addserv';
	var nice_names = {'haproxy': 'HAProxy', 'nginx': 'NGINX', 'apache': 'Apache'};
	if ($('#' + service + '_syn_flood').is(':checked')) {
		syn_flood = '1';
	}
	if ($('#' + service + '_docker').is(':checked')) {
		docker = '1';
	}
	if ($(select_id).val() == '------' || $(select_id).val() === null) {
		var select_server = $('#translate').attr('data-select_server');
		toastr.warning(select_server);
		return false
	}
	var jsonData = {};
	jsonData['servers'] = {'0': {}}
	jsonData['services'] = {};
	jsonData['services'][service] = {};
	jsonData['syn_flood'] = syn_flood;
	jsonData['servers']['0']['ip'] = $(select_id).val();
	jsonData['servers']['0']['master'] = '0';
	jsonData['servers']['0']['name'] = $(select_id + ' option:selected').text();
	if (service == 'haproxy') {
		jsonData['servers']['0']['version'] = $('#hapver option:selected').val();
	}
	jsonData['services'][service]['enabled'] = 1;
	jsonData['services'][service]['docker'] = docker;
	$("#ajax").html(wait_mess);
	$.ajax({
		url: "/app/install/" + service,
		500: function () {
			showErrorStatus(nice_names[service], $(select_id + ' option:selected').text());
		},
		504: function () {
			showErrorStatus(nice_names[service], $(select_id + ' option:selected').text());
		},
		data: {
			jsonData: JSON.stringify(jsonData),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			try {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				}
			} catch (e) {
				parseAnsibleJsonOutput(data, nice_names[service], select_id);
				$(select_id).trigger("selectmenuchange");
			}
		}
	});
}
function installExporter(exporter) {
	$("#ajaxmon").html('');
	$("#ajaxmon").html(wait_mess);
	var exporter_id = '#' + exporter + '_exp_addserv';
	var ext_prom = 0;
		if ($('#' + exporter + '_ext_prom').is(':checked')) {
			ext_prom = '1';
		}
	var nice_names = {'haproxy': 'HAProxy exporter', 'nginx': 'NGINX exporter', 'apache': 'Apache exporter', 'node': 'Node exporter', 'keepalived': 'Keepalived exporter'};
	$("#ajax").html(wait_mess);
	$.ajax({
		url: "/app/install/exporter/" + exporter,
		500: function () {
			showErrorStatus(nice_names[exporter], $(exporter_id + ' option:selected').text());
		},
		504: function () {
			showErrorStatus(nice_names[exporter], $(exporter_id + ' option:selected').text());
		},
		data: {
				server_ip: $(exporter_id).val(),
				exporter_v: $('#' + exporter + 'expver').val(),
				ext_prom: ext_prom,
				token: $('#token').val()
			},
		type: "POST",
		success: function (data) {
			try {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				}
			} catch (e) {
				parseAnsibleJsonOutput(data, nice_names[exporter], exporter_id);
				$(exporter_id).trigger("selectmenuchange");
			}
		}
	});
}
function showExporterVersion(exporter) {
	var nice_names = {'haproxy': 'HAProxy', 'nginx': 'NGINX', 'apache': 'Apache', 'node': 'Node', 'keepalived': 'Keepalived'};
	$.ajax({
			url: "/app/install/exporter/"+ exporter +"/version/" + $('#' + exporter + '_exp_addserv option:selected').val(),
			// data: {
			// 	token: $('#token').val()
			// },
			// type: "POST",
			success: function (data) {
				data = data.replace(/^\s+|\s+$/g, '');
				if (data.indexOf('error:') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else if (data == 'no' || data.indexOf('command') != '-1' || data.indexOf('_exporter:') != '-1' || data == '') {
					$('#cur_'+ exporter +'_exp_ver').text(nice_names[exporter]+' exporter has not been installed');
				} else {
					$('#cur_'+ exporter +'_exp_ver').text(data);
				}
			}
		});
}
function showServiceVersion(service) {
	$.ajax({
		url: "/app/install/" + service + "/version/" + $('#' + service + 'addserv option:selected').val(),
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('error: ') != '-1') {
				toastr.warning(data);
				$('#cur_' + service + '_ver').text('');
			} else if(data.indexOf('bash') != '-1' || data.indexOf('such') != '-1' || data.indexOf('command not found') != '-1' || data.indexOf('from') != '-1') {
				$('#cur_' + service + '_ver').text(service + ' has not installed');
				$('#' + service + '_install').text('Install');
				$('#' + service + '_install').attr('title', 'Install');
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.warning(data);
			} else if (data == '') {
				$('#cur_' + service + '_ver').text(service + ' has not installed');
				$('#' + service + '_install').text('Install');
				$('#' + service + '_install').attr('title', 'Install');
			} else {
				$('#cur_' + service + '_ver').text(data);
				$('#cur_' + service + '_ver').css('font-weight', 'bold');
				$('#' + service + '_install').text('Update');
				$('#' + service + '_install').attr('title', 'Update');
			}
		}
	});
}
function showErrorStatus(service_name, server) {
	var something_wrong = $('#translate').attr('data-something_wrong');
	toastr.error(something_wrong + ' ' + service_name + ' ' + server);
}
function parseAnsibleJsonOutput(output, service_name, select_id) {
	output = JSON.parse(JSON.stringify(output));
	var check_apache_log = $('#translate').attr('data-check_apache_log');
	var was_installed = $('#translate').attr('data-was_installed');
	for (var k in output['ok']) {
		var server_name = $(select_id + ' option[value="'+k+'"]').text();
		toastr.success(service_name + ' ' + was_installed +' ' + server_name);
	}
	for (var k in output['failures']) {
		var server_name = $(select_id + ' option[value="'+k+'"]').text();
		showErrorStatus(service_name, server_name);
	}
	for (var k in output['dark']) {
		var server_name = $(select_id + ' option[value="'+k+'"]').text();
		showErrorStatus(service_name, server_name);
	}
}
