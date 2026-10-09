function showOverviewWaf(serv, hostname) {
	let service = cur_url[0];
	if (service === 'haproxy') {
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
	let server_id = name.split('-')[1]
	$.ajax({
		url: "/waf/metric/enable/" + enable + "/" + server_id,
		type: "POST",
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
				runInstallationTaskCheck(data.tasks_ids);
				$("#ajax").html('');
			}
		}
	});
}
function changeWafMode(id) {
	let waf_mode = $('#' + id).val();
	let server_hostname = id.split('_')[0];
	let service = cur_url[0];
	$.ajax({
		url: "/waf/" + service + "/mode/" + server_hostname + "/" + waf_mode,
		type: "POST",
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
	const editor = $('#saveconfig[data-waf-editor]');
	editor.on('submit', function (event) {
		event.preventDefault();
		if (editor.data('saving')) return;
		const submitter = event.originalEvent && event.originalEvent.submitter;
		const action = submitter ? submitter.value : 'save';
		myCodeMirror.save();
		const payload = {};
		editor.serializeArray().forEach(function (field) { payload[field.name] = field.value; });
		payload.config = myCodeMirror.getValue();
		payload.action = action;
		const buttons = editor.find(':submit');
		editor.data('saving', true);
		buttons.prop('disabled', true);
		$.ajax({
			url: editor.attr('action'), type: 'POST', dataType: 'json',
			contentType: 'application/json; charset=utf-8', data: JSON.stringify(payload),
			suppressGlobalError: true,
			success: function (data) {
				toastr.clear();
				if (data.status !== 'ok') {
					toastr.error(editor.attr('data-save-error'));
					return;
				}
				toastr.success(editor.attr('data-' + action + '-success'));
				if (myCodeMirror.getValue() === payload.config) $(window).off('beforeunload');
			},
			error: function () {
				toastr.clear();
				toastr.error(editor.attr('data-save-error'));
			},
			complete: function () {
				editor.data('saving', false);
				buttons.prop('disabled', false);
			}
		});
	});
	$("#waf_rules input").change(function () {
		let id = $(this).attr('id').split('-');
		waf_rules_en(id[1])
	});
});
function waf_rules_en(id) {
	let enable = 0;
	let cur_url = window.location.href.split('/');
	let serv = cur_url[5];
	if ($('#rule_id-' + id).is(':checked')) {
		enable = '1';
	}
	$.ajax({
		url: "/waf/" + serv + "/rule/" + id + "/" + enable,
		type: "POST",
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
	const dialog = $("#add-new-config");
	if (dialog.data('creating')) return;
	const form = $('#waf-create-form');
	const error = $('#waf-create-error');
	form.off('submit.wafCreate').on('submit.wafCreate', function (event) {
		event.preventDefault();
		if (dialog.data('creating')) return;
		error.prop('hidden', true).text('');
		const payload = {
			new_waf_rule: $('#new_rule_name').val().trim(),
			new_rule_description: $('#new_rule_description').val().trim(),
			new_rule_file: $('#new_rule_file').val().trim()
		};
		if (!payload.new_rule_file.endsWith('.conf')) payload.new_rule_file += '.conf';
		if (!payload.new_waf_rule || !payload.new_rule_description ||
			payload.new_waf_rule.length > 255 || payload.new_rule_description.length > 4096 ||
			payload.new_rule_file.length > 255 || !/^[A-Za-z0-9_][A-Za-z0-9._-]*\.conf$/.test(payload.new_rule_file) ||
			Object.values(payload).some(value => /[\x00-\x1f\x7f]/.test(value))) {
			error.text(dialog.attr('data-invalid-error')).prop('hidden', false);
			return;
		}
		dialog.data('creating', true);
		const buttons = dialog.dialog('widget').find('button');
		buttons.prop('disabled', true);
		form.find('input').prop('disabled', true);
		$.ajax({
			url: dialog.attr('data-create-url'),
			data: JSON.stringify(payload),
			contentType: 'application/json; charset=utf-8',
			dataType: 'json',
			type: 'POST',
			suppressGlobalError: true,
			success: function (data) {
				if (data.status === 'Ok' && data.edit_url) {
					window.location.assign(data.edit_url);
				} else {
					error.text(dialog.attr('data-create-error')).prop('hidden', false);
				}
			},
			error: function (xhr) {
				const key = {400: 'invalid', 403: 'forbidden', 409: 'conflict'}[xhr.status] || 'create';
				error.text(dialog.attr('data-' + key + '-error')).prop('hidden', false);
			},
			complete: function () {
				dialog.data('creating', false);
				buttons.prop('disabled', false);
				form.find('input').prop('disabled', false);
			}
		});
	});
	dialog.dialog({
		autoOpen: true,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: dialog.attr('data-title'),
		beforeClose: function () { return !dialog.data('creating'); },
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: [
			{text: dialog.attr('data-create-label'), click: function () { form.trigger('submit'); }},
			{text: dialog.attr('data-cancel-label'), click: function () { dialog.dialog('close'); }}
		]
	});
}
