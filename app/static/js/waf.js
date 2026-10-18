function wafErrorMessage(xhr, fallback) {
	const message = xhr.responseJSON && typeof xhr.responseJSON.error === 'string'
		? xhr.responseJSON.error : fallback;
	return $('<div>').text(message).html();
}
function refreshWafState(context) {
	$(context).find('[data-waf-apply]').addBack('[data-waf-apply]').each(function () {
		const panel = $(this);
		if (panel.data('applying') || panel.data('confirming')) return;
		const request = (panel.data('state-request') || 0) + 1;
		panel.data('state-request', request);
		function current() {
			return panel[0].isConnected && !panel.data('applying') && !panel.data('confirming') && panel.data('state-request') === request;
		}
		$.ajax({
			url: panel.attr('data-state-url'), dataType: 'html', suppressGlobalError: true,
			success: function (html) { if (current()) panel.replaceWith(html); },
			error: function () {
				if (current()) panel.attr('data-state', 'unknown').find('[data-waf-apply-label]')
					.text(panel.attr('data-unknown')).attr('title', panel.attr('data-scope'));
			}
		});
	});
}
function confirmWafApply(button) {
	const panel = $(button).closest('[data-waf-apply]').length
		? $(button).closest('[data-waf-apply]') : $(button).closest('[data-waf-card]').find('[data-waf-apply]');
	if (!panel.length || panel.data('applying') || panel.data('confirming')) return;
	panel.data('confirming', true);
	RoxywiUI.confirm({
		title: panel.attr('data-action-label'),
		message: panel.attr('data-confirm'),
		confirmText: panel.attr('data-action-label'),
		cancelText: panel.attr('data-cancel-label')
	}).then(function (confirmed) {
		panel.data('confirming', false);
		if (!confirmed) { refreshWafState(panel); return; }
		if (!panel[0].isConnected || panel.data('applying')) return;
		panel.data('applying', true).attr('data-state', 'pending');
		panel.find('[data-waf-apply-label]').text(panel.attr('data-pending')).attr('title', panel.attr('data-apply-hint'));
		const buttons = panel.find('[data-waf-apply-button]').add($(button));
		buttons.prop('disabled', true).attr('aria-disabled', 'true');
		$.ajax({
			url: panel.attr('data-apply-url'), type: 'POST', dataType: 'json',
			contentType: 'application/json; charset=utf-8', suppressGlobalError: true,
			success: function (data) {
				toastr.clear();
				if (data && data.status === 'ok') toastr.success(panel.attr('data-success'));
				else toastr.error(panel.attr('data-error'));
			},
			error: function (xhr) { toastr.clear(); toastr.error(wafErrorMessage(xhr, panel.attr('data-error'))); },
			complete: function () {
				panel.data('applying', false);
				buttons.prop('disabled', false).removeAttr('aria-disabled');
				const slot = panel.closest('[data-waf-slot]');
				if (slot.length) showOverviewWafCallBack(slot.attr('id'));
				else refreshWafState(panel);
			}
		});
	});
}
function showOverviewWaf(serv, hostname) {
	let i;
	for (i = 0; i < serv.length; i++) {
		showOverviewWafCallBack(serv[i], hostname[i])
	}
}
function showOverviewWafCallBack(serv, hostname) {
	const slot = $(document.getElementById(serv));
	const state = slot.find('[data-waf-apply]');
	if (!slot.length || slot.data('loading') || state.data('applying') || state.data('confirming') || slot.find('.waf_mode').data('saving-mode') || slot.find('.ajaxwafstatus input').data('saving-metrics')) return;
	slot.data('loading', true).attr('aria-busy', 'true');
	$.ajax({
		url: slot.attr('data-overview-url'),
		suppressGlobalError: true,
		success: function (data) {
			const content = slot.find('[data-waf-content]');
			content.find('select').each(function () { if ($(this).selectmenu('instance')) $(this).selectmenu('destroy'); });
			content.html(data);
			content.find('select').selectmenu();
			content.find('input[type=checkbox]').checkboxradio();
			content.find('button').not('.admin-actions button').button();
			slot.find('[data-waf-error]').prop('hidden', true);
			if (window.FontAwesome) FontAwesome.dom.i2svg({node: content[0]});
		},
		error: function () {
			slot.find('[data-waf-error]').prop('hidden', false);
			slot.find('.service-card').attr('data-service-status', 'stale');
		},
		complete: function () {
			slot.data('loading', false).attr('aria-busy', 'false');
			filterServiceCards();
		}
	});
}
function metrics_waf(name) {
	const checkbox = $(document.getElementById(name));
	if (checkbox.prop('disabled') || checkbox.data('saving-metrics')) return;
	const requested = checkbox.prop('checked');
	const previous = !requested;
	const fallback = checkbox.closest('.ajaxwafstatus').attr('data-error');
	function refresh(checked, disabled) {
		checkbox.prop('checked', checked).prop('disabled', disabled);
		if (checkbox.checkboxradio('instance')) checkbox.checkboxradio('refresh');
	}
	function failure(xhr) {
		refresh(previous, false);
		toastr.error(wafErrorMessage(xhr, fallback));
	}
	checkbox.data('saving-metrics', true);
	refresh(requested, true);
	$.ajax({
		url: "/waf/metric/enable/" + Number(requested) + "/" + name.split('-')[1],
		type: "POST",
		dataType: 'json', suppressGlobalError: true,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (!data || data.status !== 'Ok') { failure({responseJSON: data}); return; }
			// The page renders charts for the servers with metrics enabled.
			window.location.reload();
		},
		error: failure,
		complete: function () { checkbox.data('saving-metrics', false); }
	});
}
function installWaf(ip1, service) {
	$("#ajax").html('');
	$("#ajax").html(wait_mess);
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
	const select = $('#' + id);
	const message = select.closest('[data-waf-mode]').find('[data-waf-mode-message]');
	function refresh(value, disabled) {
		select.val(value).prop('disabled', disabled);
		if (select.selectmenu('instance')) select.selectmenu('option', 'disabled', disabled).selectmenu('refresh');
	}
	if (select.data('saving-mode')) {
		refresh(select.data('requested-mode'), true);
		return;
	}
	if (select.prop('disabled')) return;
	const previous = select.attr('data-confirmed-mode');
	const requested = select.val();
	const url = select.find('option:selected').attr('data-save-url');
	if (!url || requested === previous) return;
	function failure(key) {
		refresh(previous, true);
		const text = select.attr('data-' + key + '-error');
		message.text(text);
		toastr.clear();
		toastr.error(text);
	}
	select.data('saving-mode', true).data('requested-mode', requested);
	message.empty();
	refresh(requested, true);
	$.ajax({
		url: url,
		type: "POST",
		dataType: 'json',
		contentType: "application/json; charset=utf-8",
		suppressGlobalError: true,
		success: function (data) {
			if (!data || data.status !== 'Ok' || data.mode !== requested) {
				failure('failed');
				return;
			}
			select.attr('data-confirmed-mode', requested);
			toastr.clear();
			toastr.info(select.attr('data-save-success'));
		},
		error: function (xhr) {
			failure({400: 'invalid', 403: 'forbidden', 409: 'conflict'}[xhr.status] || 'failed');
		},
		complete: function () {
			select.data('saving-mode', false);
			refresh(select.val(), false);
			refreshWafState(select.closest('[data-waf-card]'));
		}
	});
}
$( function() {
	$(document).off('click.wafRetry', '[data-waf-retry]').on('click.wafRetry', '[data-waf-retry]', function () {
		showOverviewWafCallBack($(this).closest('[data-waf-slot]').attr('id'));
	});
	$(document).off('change.wafMetrics', '.ajaxwafstatus input').on('change.wafMetrics', '.ajaxwafstatus input', function () {
		metrics_waf(this.id);
	});
	$(document).off('click.wafDelete', '[data-waf-delete]').on('click.wafDelete', '[data-waf-delete]', function () {
		deleteWafRule(this);
	});
	$(document).off('click.wafApply', '[data-waf-apply-button]').on('click.wafApply', '[data-waf-apply-button]', function () {
		confirmWafApply(this);
	});
	$(document).off('selectmenuchange.wafMode', '.waf_mode').on('selectmenuchange.wafMode', '.waf_mode', function () {
		changeWafMode(this.id);
	});
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
				if (!data || data.status !== 'ok') {
					toastr.error(editor.attr('data-save-error'));
					return;
				}
				toastr.success(editor.attr('data-' + action + '-success'));
				if (myCodeMirror.getValue() === payload.config) $(window).off('beforeunload');
			},
			error: function (xhr) {
				toastr.clear();
				toastr.error(wafErrorMessage(xhr, editor.attr('data-save-error')));
			},
			complete: function () {
				editor.data('saving', false);
				buttons.prop('disabled', false);
				refreshWafState(document);
			}
		});
	});
	$("#waf_rules input").change(function () {
		let id = $(this).attr('id').split('-');
		waf_rules_en(id[1])
	});
});
function waf_rules_en(id) {
	const checkbox = $('#rule_id-' + id);
	const row = $('#rule-' + id);
	const table = $('#waf_rules');
	function refresh(checked, disabled) {
		checkbox.prop('checked', checked).prop('disabled', disabled);
		if (checkbox.checkboxradio('instance')) checkbox.checkboxradio('refresh');
	}
	if (row.data('deleting')) {
		refresh(row.attr('data-enabled') === '1', true);
		return;
	}
	if (row.data('toggling')) {
		refresh(row.data('requested') === 1, true);
		return;
	}
	const previous = row.attr('data-enabled') === '1';
	const enable = checkbox.is(':checked') ? 1 : 0;
	function failure(key) {
		refresh(previous, true);
		toastr.clear();
		toastr.error(table.attr('data-' + key + '-error'));
	}
	row.data('toggling', true).data('requested', enable);
	row.find('[data-waf-delete]').prop('disabled', true);
	refresh(enable === 1, true);
	$.ajax({
		url: row.attr(enable ? 'data-enable-url' : 'data-disable-url'),
		type: "POST",
		dataType: 'json',
		contentType: "application/json; charset=utf-8",
		suppressGlobalError: true,
		success: function (data) {
			if (!data || data.status !== 'updated' || data.enabled !== enable) {
				failure('toggle');
				return;
			}
			row.attr('data-enabled', String(enable)).addClass('update');
			refresh(enable === 1, true);
			toastr.clear();
			toastr.info(table.attr('data-toggle-success'));
			setTimeout(function () { row.removeClass('update'); }, 2500);
		},
		error: function (xhr) {
			failure({400: 'invalid', 403: 'forbidden', 409: 'conflict'}[xhr.status] || 'toggle');
		},
		complete: function () {
			row.data('toggling', false);
			row.find('[data-waf-delete]').prop('disabled', false);
			refresh(checkbox.is(':checked'), false);
			refreshWafState(document);
		}
	});
}
function deleteWafRule(button) {
	const row = $(button).closest('tr');
	const table = $('#waf_rules');
	if (row.data('deleting') || row.data('toggling')) return;
	function unlock() {
		if (!row[0].isConnected) return;
		row.data('deleting', false);
		row.find('button, input').prop('disabled', false);
		row.find('input[type="checkbox"]').checkboxradio('refresh');
	}
	row.data('deleting', true);
	row.find('button, input').prop('disabled', true);
	row.find('input[type="checkbox"]').checkboxradio('refresh');
	RoxywiUI.confirm({
		title: table.attr('data-delete-title'),
		message: table.attr('data-delete-confirm') + ' ' + row.attr('data-rule-name') + ' · ' + table.attr('data-server'),
		confirmText: table.attr('data-delete-label'), cancelText: table.attr('data-cancel-label')
	}).then(function (confirmed) {
		if (!confirmed || !row[0].isConnected) { unlock(); return; }
		$.ajax({
			url: row.attr('data-delete-url'), type: 'DELETE', dataType: 'json',
			contentType: 'application/json; charset=utf-8', suppressGlobalError: true,
			success: function (data) {
				toastr.clear();
				if (data && data.status === 'deleted' && data.id === Number(row.attr('data-rule-id'))) {
					row.remove();
					toastr.info(table.attr('data-delete-success'));
				} else toastr.error(table.attr('data-delete-error'));
			},
			error: function (xhr) { toastr.clear(); toastr.error(wafErrorMessage(xhr, table.attr('data-delete-error'))); },
			complete: function () { unlock(); refreshWafState(document); }
		});
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
				refreshWafState(document);
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
