var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('/');
function showHapservers(serv, hostnamea, service) {
	let nextIndex = 0;
	let activeRequests = 0;
	const concurrency = 2;

	function runNext() {
		while (activeRequests < concurrency && nextIndex < serv.length) {
			const index = nextIndex++;
			activeRequests += 1;
			showHapserversCallBack(serv[index], hostnamea[index], service).always(function () {
				activeRequests -= 1;
				runNext();
			});
		}
	}
	runNext();
}
function showHapserversCallBack(serv, hostnamea, service) {
	const lastEdit = $("#edit_date_" + hostnamea);
	function markUnavailable() {
		lastEdit.empty().text('—').attr('title', translate_div.attr('data-unavailable') || 'Unavailable');
	}
	return $.ajax({
		url: "/service/" + service + "/" + serv + "/last-edit",
		beforeSend: function () {
			lastEdit.html('<img class="loading_small_haproxyservers" src="/static/images/loading.gif" />');
		},
		type: "GET",
		suppressGlobalError: true,
		success: function (data) {
			const value = String(data || '').trim();
			if (!value || value.indexOf('ls: cannot access') !== -1 || value.toLocaleLowerCase().indexOf('error:') === 0) {
				markUnavailable();
			} else {
				lastEdit.empty().text(value).removeAttr('title');
			}
		},
		error: markUnavailable
	});
}
function overviewHapserverBackends(serv, hostname, service) {
	let div = '';
	$.ajax( {
		url: `/service/${service}/${serv[0]}/backend`,
		beforeSend: function() {
			$("#top-"+hostname).html('<img class="loading_small" style="padding-left: 45%;" src="/static/images/loading.gif" />');
		},
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				$('.div-backends').css('height', 'auto');
				$("#top-" + hostname).empty();
				for (let i in data.data) {
					if (service === 'haproxy') {
						div = `<a href="/config/haproxy/${serv}/show/?section=${data.data[i]}" target="_blank" style="padding-right: 10px;">${data.data[i]}</a> `
					} else if (service === 'nginx' || service === 'apache') {
						div = `<a href="/config/${service}/${serv}/show/${i}" target="_blank" style="padding-right: 10px;">${data.data[i]}</a>`;
					} else {
						div = data.data[i];
					}
					$("#top-" + hostname).append(div);
				}
			}
		}
	} );
}
function showOverview(serv, hostnamea) {
	showOverviewHapWI();
	showUsersOverview();
	let i;
	for (i = 0; i < serv.length; i++) {
		showOverviewCallBack(serv[i], hostnamea[i])
	}
	showSubOverview();
	showServicesOverview();
	updatingCpuRamCharts();
}
function showOverviewCallBack(serv, hostnamea) {
	$.ajax( {
		url: "/overview/server/"+serv,
		beforeSend: function() {
			$("#"+hostnamea).html('<img class="loading_small" src="/static/images/loading.gif" />');
		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
				$("#"+hostnamea).html("");
			} else {
				$("#" + hostnamea).empty();
				$("#" + hostnamea).html(data);
			}
		}
	} );
}
function showServicesOverview() {
	$.ajax( {
		url: "/overview/services",
		beforeSend: function() {
			$("#services_ovw").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');

		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#services_ovw").empty();
				$("#services_ovw").html(data);
			}
		}
	} );
}
function showOverviewServer(name, ip, id, service) {
	$.ajax( {
		url: "/service/cpu-ram-metrics/" + ip + "/" + id + "/" + name + "/" + service,
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#ajax-server-" + id).empty();
				$(".ajax-server").css('display', 'block');
				$(".div-server").css('clear', 'both');
				$(".div-pannel").css('clear', 'both');
				$(".div-pannel").css('display', 'block');
				$(".div-pannel").css('padding-top', '10px');
				$(".div-pannel").css('height', '70px');
				$("#div-pannel-" + id).insertBefore('#up-pannel')
				$("#ajax-server-" + id).html(data);
				$.getScript(awesome)
				getChartDataHapWiRam(ip)
				getChartDataHapWiCpu(ip)
			}
		}					
	} );
}
function ajaxActionServers(action, id, service) {
	$.ajax({
		url: "/service/" + service + "/" + id + "/" + action,
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				location.reload();
			}
		}
	});
}
$( function() {
	try {
		if ((cur_url[0] == 'service' && cur_url[2] != '') || cur_url[0] == '') {
			ChartsIntervalId = setInterval(updatingCpuRamCharts, 30000);
			$(window).focus(function () {
				ChartsIntervalId = setInterval(updatingCpuRamCharts, 30000);
			});
			$(window).blur(function () {
				clearInterval(ChartsIntervalId);
			});
		}
	} catch (e) {
		console.log(e);
	}
	try {
		if (cur_url[0] == '') {
			UsersShowIntervalId = setInterval(showUsersOverview, 600000);
			$(window).focus(function () {
				UsersShowIntervalId = setInterval(showUsersOverview, 600000);
			});
			$(window).blur(function () {
				clearInterval(UsersShowIntervalId);
			});
		}
	} catch (e) {
		console.log(e);
	}
	$( "#show-all-users" ).click( function() {
		$(".show-users").show("fast");
		$("#hide-all-users").css("display", "block");
		$("#show-all-users").css("display", "none");
	});
	$("#hide-all-users").click(function() {
		$(".show-users").hide("fast");
		$("#hide-all-users").css("display", "none");
		$("#show-all-users").css("display", "block");
	});

	$( "#show-all-groups" ).click( function() {
		$(".show-groups").show("fast");
		$("#hide-all-groups").css("display", "block");
		$("#show-all-groups").css("display", "none");
	});
	$( "#hide-all-groups" ).click( function() {
		$(".show-groups").hide("fast");
		$("#hide-all-groups").css("display", "none");
		$("#show-all-groups").css("display", "block");
	});

	if (cur_url[0] == "" || cur_url[0] == "waf" || cur_url[0] == "metrics") {
		$('#secIntervals').css('display', 'none');
	}
	$( ".server-act-links" ).change(function() {
		let id = $(this).attr('id').split('-');

		if (cur_url[0] != 'portscanner') {
			try {
				var service_name = id[2]
			} catch (err) {
				var service_name = 'haproxy'
			}

			updateHapWIServer(id[1], service_name)
		}
	});
});
function confirmAjaxAction(action, service, id) {
	let action_word = translate_div.attr('data-'+action);
	let name = $('#server-name-'+id).val();
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: action_word + " " + name + "?",
		buttons: [{
			text: action_word,
			click: function () {
				$(this).dialog("close");
				if (service === "waf") {
					ajaxActionServers(action, id, 'waf_haproxy');
				} else {
					ajaxActionServers(action, id, service);
				}
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function updateHapWIServer(id, service_name) {
	let alert_en = 0;
	let metrics = 0;
	let active = 0;
	if ($('#alert-' + id).is(':checked')) {
		alert_en = '1';
	}
	if ($('#metrics-' + id).is(':checked')) {
		metrics = '1';
	}
	if ($('#active-' + id).is(':checked')) {
		active = '1';
	}
	$.ajax({
		url: "/service/" + service_name + "/tools/update",
		data: {
			server_id: id,
			name: $('#server-name-' + id).val(),
			metrics: metrics,
			alert_en: alert_en,
			active: active
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#server-" + id + "-" + service_name).addClass("update", 1000);
				setTimeout(function () {
					$("#server-" + id + "-" + service_name).removeClass("update");
				}, 2500);
			}
		}
	});
}
function change_pos(pos, id) {
	$.ajax({
		url: "/service/position/" + id + "/" + pos,
		suppressGlobalError: true,
		error: function (xhr) {
			const parsed = window.RoxywiUI
				? window.RoxywiUI.parseResponse(xhr.responseJSON || xhr.responseText)
				: {summary: xhr.statusText || 'Cannot save server position'};
			toastr.error(parsed.summary);
		}
	});
}
function showBytes(serv) {
	$.ajax( {
		url: "/service/haproxy/bytes/" + serv,
		beforeSend: function() {
			$("#show_bin_bout").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
			$("#sessions").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function showNginxConnections(serv) {
	$.ajax( {
		url: "/service/nginx/connections/" + serv,
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function showApachekBytes(serv) {
	$.ajax( {
		url: "/service/apache/bytes/" + serv,
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function keepalivedBecameMaster(serv) {
	$.ajax( {
		url: "/service/keepalived/become-master/" + serv,
		beforeSend: function() {
			$("#bin_bout").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function showUsersOverview() {
	$.ajax( {
		url: "overview/users",
		type: "GET",
		beforeSend: function() {
			$("#users-table").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#users-table").html(data);
			}
		}
	} );
}
function showSubOverview() {
	$.ajax( {
		url: "/overview/sub",
		type: "GET",
		beforeSend: function() {
			$("#sub-table").html('<img class="loading_small_bin_bout" style="padding-left: 40%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#sub-table").html(data);
			}
		}
	} );
}
function serverSettings(id, name) {
	let settings_word = translate_div.attr('data-settings');
	let for_word = translate_div.attr('data-for');
	let service = $('#service').val();
	$.ajax({
		url: "/service/settings/" + service + "/" + id,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#dialog-settings-service").html(data)
				$("input[type=checkbox]").checkboxradio();
				$("#dialog-settings-service").dialog({
					resizable: false,
					height: "auto",
					width: 400,
					modal: true,
					title: settings_word + " " + for_word + " " + name,
					buttons: [{
						text: save_word,
						click: function () {
							$(this).dialog("close");
							serverSettingsSave(id, name, service, $(this));
						}
					}, {
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}]
				});
			}
		}
	});
}
function serverSettingsSave(id, name, service, dialog_id) {
	let service_dockerized = 0;
	let service_restart = 0;
	if ($('#haproxy_dockerized').is(':checked')) {
		service_dockerized = '1';
	}
	if ($('#nginx_dockerized').is(':checked')) {
		service_dockerized = '1';
	}
	if ($('#apache_dockerized').is(':checked')) {
		service_dockerized = '1';
	}
	if ($('#haproxy_restart').is(':checked')) {
		service_restart = '1';
	}
	if ($('#nginx_restart').is(':checked')) {
		service_restart = '1';
	}
	if ($('#apache_restart').is(':checked')) {
		service_restart = '1';
	}
	$.ajax({
		url: "/service/settings/" + service,
		data: {
			serverSettingsSave: id,
			serverSettingsDockerized: service_dockerized,
			serverSettingsRestart: service_restart,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				dialog_id.dialog('close');
				location.reload();
			}
		}
	});
}
function check_service_status(id, ip, service) {
	if (sessionStorage.getItem('check-service-'+service+'-'+id) === '0') {
		return false;
	}
	NProgress.configure({showSpinner: false});
	let server_div = $('#div-server-' + id);
	$.ajax({
		url: "/service/" + service + "/" + id + "/status",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			401: function (xhr) {
				sessionStorage.setItem('check-service-'+service+'-'+id, '0')
			},
			404: function (xhr) {
				sessionStorage.setItem('check-service-'+service+'-'+id, '0')
			},
			500: function (xhr) {
				sessionStorage.setItem('check-service-'+service+'-'+id, '0')
			}
		},
		success: function (data) {
			if (cur_url[0] === 'overview') {
				let span_id = $('#' + service + "_" + id);
				if (data.status === 'failed') {
					span_id.addClass('serverDown');
					span_id.removeClass('serverUp');
					span_id.attr('title', 'Service is down')
				} else {
					span_id.addClass('serverUp');
					span_id.removeClass('serverDown');
					if (span_id.attr('title').indexOf('Service is down') != '-1') {
						span_id.attr('title', 'Service running')
					}
				}
			} else {
				applyServiceStatus(data);
			}
		}
	});
	NProgress.configure({showSpinner: true});
}

function serviceStatusLabel(status) {
	const labels = {
		running: translate_div.attr('data-running') || 'Running',
		stopped: translate_div.attr('data-stopped') || 'Stopped',
		unavailable: translate_div.attr('data-unavailable') || 'Unavailable',
		stale: translate_div.attr('data-stale') || 'Stale'
	};
	return labels[status] || labels.unavailable;
}

function applyServiceStatus(data) {
	const id = data.server_id;
	const card = $('#div-server-' + id);
	if (!card.length) return;
	let status = data.status;
	if (status === 'failed' || data.error) status = 'unavailable';
	if (status !== 'running' && status !== 'stopped') status = 'unavailable';

	card.attr('data-service-status', status)
		.removeClass('div-server-head-up div-server-head-down div-server-head-dis div-server-head-unknown')
		.addClass(status === 'running' ? 'div-server-head-up' : (status === 'stopped' ? 'div-server-head-down' : 'div-server-head-unknown'));
	$('#service-status-' + id)
		.removeClass('rw-status-running rw-status-stopped rw-status-unavailable rw-status-stale')
		.addClass('rw-status-' + status)
		.text(serviceStatusLabel(status));
	if (status !== 'unavailable') {
		$('#uptime-word-' + id).text(status === 'running' ? translate_div.attr('data-uptime') : translate_div.attr('data-downtime'));
		$('#service-version-' + id).text(data.Version || '—');
		$('#service-process_num-' + id).text(data.Process ?? '—');
		$('#service-uptime-' + id).text(data.Uptime || '—');
	}
	const now = new Date();
	card.attr('data-last-checked', now.toISOString());
	$('#service-last-checked-' + id).text(now.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}));
}

function filterServiceCards() {
	const query = ($('#service-server-search').val() || '').trim().toLocaleLowerCase();
	const status = $('#service-status-filter').val() || 'all';
	$('.service-card').each(function () {
		const card = $(this);
		const matchesText = !query || (card.attr('data-server-name') || '').indexOf(query) !== -1 || card.text().toLocaleLowerCase().indexOf(query) !== -1;
		const matchesStatus = status === 'all' || card.attr('data-service-status') === status;
		card.toggle(matchesText && matchesStatus);
	});
}

function initializeServiceStatusPolling(service, serverIds) {
	if (!serverIds || !serverIds.length) return;
	const statusBatchSize = 2;
	const statusBatchConcurrency = 3;
	let timer = null;
	let retryDelay = 11000;
	let stopped = false;
	let loading = false;
	const summary = $('#service-poll-summary');
	const summaryValue = summary.find('.service-poll-summary-value');
	const statusFilter = $('#service-status-filter');
	let statusFilterReady = false;

	function setSummary(value, updating) {
		summaryValue.text(value);
		summary.toggleClass('is-updating', Boolean(updating));
	}
	function enableStatusFilter() {
		if (statusFilterReady || !statusFilter.length) return;
		statusFilterReady = true;
		statusFilter.prop('disabled', false);
		try { statusFilter.selectmenu('enable').selectmenu('refresh'); } catch (error) { /* Native select remains usable. */ }
	}

	function markStale(ids) {
		(ids || serverIds).forEach(function (id) {
			$('#div-server-' + id)
				.attr('data-service-status', 'stale')
				.removeClass('div-server-head-up div-server-head-down div-server-head-dis div-server-head-unknown')
				.addClass('div-server-head-unknown');
			$('#service-status-' + id)
				.removeClass('rw-status-running rw-status-stopped rw-status-unavailable')
				.addClass('rw-status-stale')
				.text(serviceStatusLabel('stale'));
		});
		filterServiceCards();
	}
	function schedule(delay) {
		window.clearTimeout(timer);
		if (!stopped && !document.hidden) timer = window.setTimeout(load, delay);
	}
	function load() {
		if (document.hidden || stopped || loading) return;
		loading = true;
		const batches = [];
		for (let index = 0; index < serverIds.length; index += statusBatchSize) {
			batches.push(serverIds.slice(index, index + statusBatchSize));
		}
		let nextBatch = 0;
		let activeBatches = 0;
		let completedBatches = 0;
		let failedBatches = 0;
		const updatedServerIds = new Set();
		setSummary('0 / ' + serverIds.length, true);

		function finishCycle() {
			if (completedBatches !== batches.length) return;
			loading = false;
			enableStatusFilter();
			filterServiceCards();
			if (updatedServerIds.size === 0) {
				setSummary(serviceStatusLabel('stale'), false);
				retryDelay = Math.min(retryDelay * 2, 60000);
			} else {
				const updatedAt = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
				const partial = failedBatches || updatedServerIds.size < serverIds.length;
				setSummary(partial ? updatedServerIds.size + ' / ' + serverIds.length + ' · ' + updatedAt : updatedAt, false);
				retryDelay = 11000;
			}
			schedule(retryDelay);
		}

		function runBatches() {
			while (activeBatches < statusBatchConcurrency && nextBatch < batches.length) {
				const batchIds = batches[nextBatch++];
				activeBatches += 1;
				$.ajax({
					url: '/service/' + service + '/statuses',
					type: 'POST',
					data: JSON.stringify({server_ids: batchIds}),
					contentType: 'application/json; charset=utf-8',
					timeout: 30000,
					suppressGlobalError: true
				}).done(function (response) {
					const returnedIds = new Set();
					(response.data || []).forEach(function (data) {
						applyServiceStatus(data);
						returnedIds.add(Number(data.server_id));
						updatedServerIds.add(Number(data.server_id));
					});
					const missingIds = batchIds.filter(function (id) { return !returnedIds.has(Number(id)); });
					if (missingIds.length) {
						failedBatches += 1;
						markStale(missingIds);
					}
					enableStatusFilter();
					filterServiceCards();
					setSummary(updatedServerIds.size + ' / ' + serverIds.length, true);
				}).fail(function () {
					failedBatches += 1;
					markStale(batchIds);
				}).always(function () {
					activeBatches -= 1;
					completedBatches += 1;
					runBatches();
					finishCycle();
				});
			}
		}

		runBatches();
	}

	$('#service-server-search').on('input', filterServiceCards);
	statusFilter.on('change selectmenuchange', filterServiceCards);
	document.addEventListener('visibilitychange', function () {
		window.clearTimeout(timer);
		if (!document.hidden) load();
	});
	window.addEventListener('pagehide', function () { stopped = true; window.clearTimeout(timer); });
	load();
}

$(document).on('click', '.service-actions-toggle', function (event) {
	event.stopPropagation();
	const button = $(this);
	const menu = button.siblings('.service-actions-menu');
	const open = menu.prop('hidden');
	$('.service-actions-menu').prop('hidden', true);
	$('.service-actions-toggle').attr('aria-expanded', 'false');
	menu.prop('hidden', !open);
	button.attr('aria-expanded', String(open));
});
$(document).on('click', '.service-action-command', function () {
	const button = $(this);
	button.closest('.service-actions-menu').prop('hidden', true);
	confirmAjaxAction(button.data('action'), button.data('service'), button.data('server-id'));
});
$(document).on('click', '.service-settings-command', function () {
	serverSettings($(this).data('server-id'), $(this).data('server-name'));
});
$(document).on('click', function (event) {
	if (!$(event.target).closest('.service-actions').length) {
		$('.service-actions-menu').prop('hidden', true);
		$('.service-actions-toggle').attr('aria-expanded', 'false');
	}
});
$(document).on('click keydown', '.service-card[data-detail-url]', function (event) {
	if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
	if ($(event.target).closest('a, button, input, select, label, .ui-button').length) return;
	if (event.type === 'keydown') event.preventDefault();
	window.location.href = $(this).data('detail-url');
});
