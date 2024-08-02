function showOverviewWaf(serv, hostname) {
	let service = cur_url[0];
	if (service == 'haproxy') {
		$.getScript('/static/js/chart.min-4.3.0.js');
		showWafMetrics();
	}
	let i;
	for (i = 0; i < serv.length; i++) {
		showOverviewWafCallBack(serv[i], hostname[i])
	}
	$.getScript(overview);
	$.getScript(waf);
}
function showOverviewWafCallBack(serv, hostname) {
	let service = cur_url[0];
	$.ajax({
		url: "/waf/overview/" + service + "/" + serv,
		beforeSend: function () {
			$("#" + hostname).html('<img class="loading_small" src="/static/images/loading.gif" />');
		},
		success: function (data) {
			$("#" + hostname).empty();
			$("#" + hostname).html(data)
			$("input[type=submit], button").button();
			$("input[type=checkbox]").checkboxradio();
			$.getScript(overview);
			$.getScript(awesome);
		}
	});
}
function metrics_waf(name) {
	let enable = 0;
	if ($('#' + name).is(':checked')) {
		enable = '1';
	}
	name = name.split('metrics')[1]
	$.ajax({
		url: "/waf/metric/enable/" + enable + "/" + name,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				showOverviewWaf(ip, hostnamea);
				setTimeout(function () {
					$("#" + name).parent().parent().removeClass("update");
				}, 2500);
			}
		}
	});
}
function installWaf(ip1) {
	$("#ajax").html('');
	$("#ajax").html(wait_mess);
	let service = cur_url[0];
	$.ajax({
		url: "/install/waf/" + service + "/" + ip1,
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				parseAnsibleJsonOutput(data, `${service} WAF`, false);
				showOverviewWaf(ip, hostnamea);
				$("#ajax").html('');
			}
		}
	});
}
function changeWafMode(id) {
	let waf_mode = $('#' + id + ' option:selected').val();
	let server_hostname = id.split('_')[0];
	let service = cur_url[0];
	$.ajax({
		url: "/waf/" + service + "/mode/" + server_hostname + "/" + waf_mode,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.info('Do not forget restart WAF service');
				$('#' + server_hostname + '-select-line').addClass("update", 1000);
				setTimeout(function () {
					$('#' + server_hostname + '-select-line').removeClass("update");
				}, 2500);
			}
		}
	});
}
$( function() {
	$("#waf_rules input").change(function () {
		let id = $(this).attr('id').split('-');
		waf_rules_en(id[1])
	});
});
function waf_rules_en(id) {
	let enable = 0;
	if ($('#rule_id-' + id).is(':checked')) {
		enable = '1';
	}
	let serv = cur_url[2];
	$.ajax({
		url: "/waf/" + serv + "/rule/" + id + "/" + enable,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.info('Do not forget restart WAF service');
				$('#rule-' + id).addClass("update", 1000);
				setTimeout(function () {
					$('#rule-' + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function addNewConfig() {
	$("#add-new-config").dialog({
		autoOpen: true,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: "Create a new rule",
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Create": function () {
				let valid = true;
				let new_rule_name_id = $('#new_rule_name');
				let new_rule_description_id = $('#new_rule_description');
				allFields = $([]).add(new_rule_name_id).add(new_rule_description_id)
				allFields.removeClass("ui-state-error");
				valid = valid && checkLength(new_rule_name_id, "New rule name", 1);
				valid = valid && checkLength(new_rule_description_id, "New rule description", 1);
				if (valid) {
					let new_rule_name = new_rule_name_id.val();
					let new_rule_description = new_rule_description_id.val();
					let new_rule_file = new_rule_name.replaceAll(' ', '_');
					let service = cur_url[0];
					let serv = cur_url[2];
					service = escapeHtml(service);
					new_rule_name = escapeHtml(new_rule_name);
					new_rule_description = escapeHtml(new_rule_description);
					new_rule_file = escapeHtml(new_rule_file);
					serv = escapeHtml(serv);
					jsonData = {
						"new_waf_rule": new_rule_name,
						"new_rule_description": new_rule_description,
						"new_rule_file": new_rule_file
					}
					$.ajax({
						url: "/waf/" + service + "/" + serv + "/rule/create",
						data: JSON.stringify(jsonData),
						contentType: "application/json; charset=utf-8",
						type: "POST",
						success: function (data) {
							if (data.status === 'failed') {
								toastr.error(data.error);
							} else {
								window.location.replace("/waf/" + service + "/" + serv + "/rule/" + data.id);
							}
						}
					});
					$(this).dialog("close");
				}
			},
			Cancel: function () {
				$(this).dialog("close");
			}
		}
	});
}
