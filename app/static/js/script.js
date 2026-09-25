var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('/');
try {
	if (sessionStorage.getItem('hide_menu') === 'hide') {
		document.documentElement.classList.add('nav-collapsed');
	}
} catch (error) {
	// Navigation still works when browser storage is unavailable.
}
function validateEmail(email) {
	const re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
	return re.test(email);
}
function ValidateIPaddress(ipaddress) {
	if (/^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/.test(ipaddress)) {
		return true
	}
	return false
}
var select_server = translate_div.attr('data-select_server');
function checkIsServerFiled(select_id, message = select_server) {
	if ($(select_id).val() == null || $(select_id).val() === '') {
		toastr.warning(message);
		return false;
	}
	return true;
}
function escapeHtml(unsafe) {
	return unsafe
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}
var wait_mess_word = translate_div.attr('data-wait_mess');
var wait_mess = '<div class="alert alert-warning">'+wait_mess_word+'</div>'
function show_current_page(id) {
	activateNavigationLink(id.find('a').first().get(0));
}

function activateNavigationLink(link) {
	if (!link) {
		return;
	}
	document.querySelectorAll('#app-navigation a.menu-active').forEach(function (item) {
		item.classList.remove('menu-active');
		item.removeAttribute('aria-current');
	});
	document.querySelectorAll('#app-navigation .nav-parent-active').forEach(function (item) {
		item.classList.remove('nav-parent-active');
	});
	link.classList.add('menu-active');
	link.setAttribute('aria-current', 'page');
	let service = link.closest('.p_menu');
	if (service) {
		service.classList.add('is-open', 'nav-parent-active');
		let serviceToggle = service.querySelector('.nav-submenu-toggle');
		if (serviceToggle) {
			serviceToggle.setAttribute('aria-expanded', 'true');
		}
	}
	let group = link.closest('.nav-group');
	if (group) {
		group.classList.add('is-open');
		let groupToggle = group.querySelector(':scope > .nav-group-toggle');
		if (groupToggle) {
			groupToggle.setAttribute('aria-expanded', 'true');
		}
	}
}

function markCurrentNavigationLink() {
	let currentPath = window.location.pathname.replace(/\/$/, '') || '/';
	let currentHash = window.location.hash;
	let bestLink = null;
	let bestScore = -1;
	document.querySelectorAll('#app-navigation a[href]').forEach(function (link) {
		let target;
		try {
			target = new URL(link.href, window.location.origin);
		} catch (error) {
			return;
		}
		if (target.origin !== window.location.origin) {
			return;
		}
		let targetPath = target.pathname.replace(/\/$/, '') || '/';
		let exactPath = targetPath === currentPath;
		let childPath = targetPath !== '/' && currentPath.indexOf(targetPath + '/') === 0;
		if (!exactPath && !childPath) {
			return;
		}
		if (target.hash && currentHash && target.hash !== currentHash) {
			return;
		}
		let score = targetPath.length + (exactPath ? 10000 : 0) + (target.hash && currentHash ? 20000 : 0)
			+ (link.classList.contains('head-submenu') ? 100 : 0);
		if (score > bestScore) {
			bestScore = score;
			bestLink = link;
		}
	});
	if (bestLink) {
		activateNavigationLink(bestLink);
	}
}

function setNavigationCollapsed(collapsed) {
	document.documentElement.classList.toggle('nav-collapsed', collapsed);
	let button = document.getElementById('hide_menu');
	if (button) {
		let title = collapsed ? button.dataset.expandTitle : button.dataset.collapseTitle;
		button.setAttribute('title', title);
		button.setAttribute('aria-label', title);
		button.setAttribute('aria-pressed', String(collapsed));
	}
	try {
		sessionStorage.setItem('hide_menu', collapsed ? 'hide' : 'show');
	} catch (error) {
		// Do not block navigation when browser storage is unavailable.
	}
}

function initializeAppNavigation() {
	let navigation = document.getElementById('app-navigation');
	if (!navigation) {
		return;
	}

	$('#app-navigation button.ui-button').button('destroy');
	setNavigationCollapsed(document.documentElement.classList.contains('nav-collapsed'));
	markCurrentNavigationLink();

	navigation.querySelectorAll('.nav-group').forEach(function (group) {
		let key = 'roxywi-nav-group-' + group.dataset.navGroup;
		try {
			if (localStorage.getItem(key) === 'closed' && !group.querySelector('.menu-active')) {
				group.classList.remove('is-open');
				group.querySelector(':scope > .nav-group-toggle').setAttribute('aria-expanded', 'false');
			}
		} catch (error) {
			// Keep the default expanded state.
		}
	});

	navigation.querySelectorAll('.nav-group-toggle').forEach(function (button) {
		button.addEventListener('click', function () {
			let group = button.closest('.nav-group');
			let open = !group.classList.contains('is-open');
			group.classList.toggle('is-open', open);
			button.setAttribute('aria-expanded', String(open));
			try {
				localStorage.setItem('roxywi-nav-group-' + group.dataset.navGroup, open ? 'open' : 'closed');
			} catch (error) {
				// The group can still be toggled without persistence.
			}
		});
	});

	navigation.querySelectorAll('.nav-submenu-toggle').forEach(function (button) {
		button.addEventListener('click', function () {
			if (document.documentElement.classList.contains('nav-collapsed')) {
				setNavigationCollapsed(false);
			}
			let service = button.closest('.p_menu');
			let open = !service.classList.contains('is-open');
			service.classList.toggle('is-open', open);
			button.setAttribute('aria-expanded', String(open));
		});
	});

	let collapse = document.getElementById('hide_menu');
	if (collapse) {
		collapse.addEventListener('click', function () {
			setNavigationCollapsed(!document.documentElement.classList.contains('nav-collapsed'));
		});
	}

	let mobileToggle = document.getElementById('app-mobile-nav-toggle');
	let backdrop = document.getElementById('app-nav-backdrop');
	function setMobileNavigation(open) {
		document.documentElement.classList.toggle('nav-mobile-open', open);
		if (mobileToggle) mobileToggle.setAttribute('aria-expanded', String(open));
	}
	if (mobileToggle) {
		mobileToggle.addEventListener('click', function () {
			setMobileNavigation(!document.documentElement.classList.contains('nav-mobile-open'));
		});
	}
	if (backdrop) backdrop.addEventListener('click', function () { setMobileNavigation(false); });
	navigation.querySelectorAll('a').forEach(function (link) {
		link.addEventListener('click', function () {
			if (window.matchMedia('(max-width: 900px)').matches) setMobileNavigation(false);
		});
	});
	document.addEventListener('keydown', function (event) {
		if (event.key === 'Escape' && document.documentElement.classList.contains('nav-mobile-open')) {
			setMobileNavigation(false);
			if (mobileToggle) mobileToggle.focus();
		}
	});

	let search = document.getElementById('app-navigation-search');
	let empty = navigation.querySelector('.app-nav-empty');
	if (search) {
		search.addEventListener('input', function () {
			let query = search.value.trim().toLocaleLowerCase();
			let visibleItems = 0;
			navigation.querySelectorAll('.nav-item, .nav-service').forEach(function (item) {
				let haystack = ((item.dataset.navSearch || '') + ' ' + item.textContent).toLocaleLowerCase();
				let visible = !query || haystack.indexOf(query) !== -1;
				item.hidden = !visible;
				if (visible) {
					visibleItems += 1;
				}
			});
			navigation.querySelectorAll('.nav-group').forEach(function (group) {
				let hasVisibleItem = Array.from(group.querySelectorAll('.nav-item, .nav-service')).some(function (item) { return !item.hidden; });
				group.hidden = !hasVisibleItem;
				if (query && hasVisibleItem) {
					group.classList.add('is-open');
				}
			});
			empty.hidden = visibleItems !== 0;
		});
		search.addEventListener('keydown', function (event) {
			if (event.key === 'Escape') {
				search.value = '';
				search.dispatchEvent(new Event('input'));
				search.blur();
			}
		});
		document.addEventListener('keydown', function (event) {
			let target = event.target;
			let typing = target && (target.matches('input, textarea, select') || target.isContentEditable);
			if (event.key === '/' && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
				event.preventDefault();
				if (document.documentElement.classList.contains('nav-collapsed')) {
					setNavigationCollapsed(false);
				}
				search.focus();
			}
		});
	}
}

jQuery.expr[':'].regex = function(elem, index, match) {
    var matchParams = match[3].split(','),
        validLabels = /^(data|css):/,
        attr = {
            method: matchParams[0].match(validLabels) ?
                        matchParams[0].split(':')[0] : 'attr',
            property: matchParams.shift().replace(validLabels,'')
        },
        regexFlags = 'ig',
        regex = new RegExp(matchParams.join('').replace(/^\s+|\s+$/g,''), regexFlags);
    return regex.test(jQuery(elem)[attr.method](attr.property));
}
$( document ).ajaxSend(function( event, request, settings ) {
	NProgress.start();
});
$( document ).ajaxComplete(function( event, request, settings ) {
	NProgress.done();
});
$.ajaxSetup({
	headers: {"X-CSRF-TOKEN": csrf_token},
});
function normalizeRoxywiResponse(value) {
	if (Array.isArray(value)) {
		value = value.join('\n');
	} else if (value && typeof value === 'object') {
		value = value.error || value.message || JSON.stringify(value);
	}
	return String(value || '')
		.replace(/<br\s*\/?\s*>/gi, '\n')
		.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '')
		.replace(/\r/g, '')
		.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
}
function uniqueRoxywiMessages(messages) {
	return messages.filter(function (message, index) {
		return message && messages.indexOf(message) === index;
	});
}
function parseRoxywiResponse(value) {
	const normalized = normalizeRoxywiResponse(value);
	const separated = normalized.replace(
		/\s*(\[(?:NOTICE|WARNING|WARN|ALERT|ALER|ERROR|EMERG)\])/gi,
		'\n$1'
	);
	const lines = separated.split('\n').map(function (line) { return line.trim(); }).filter(Boolean);
	const warnings = uniqueRoxywiMessages(lines.filter(function (line) {
		return /\[(?:WARNING|WARN)\]/i.test(line);
	}));
	const errors = uniqueRoxywiMessages(lines.filter(function (line) {
		if (/\[(?:WARNING|WARN|NOTICE)\]/i.test(line)) {
			return false;
		}
		return /\[(?:ALERT|ALER|ERROR|EMERG)\]/i.test(line)
			|| /(^|\s)(?:error|fatal|failed|failure|emerg|syntax error|unexpected|unknown)(?:[.:]|\s|$)/i.test(line);
	}));

	const inactiveMatch = normalized.match(
		/([A-Za-z0-9_.@-]+\.service is not active, cannot reload\.?)|([A-Za-z0-9_.@-]+: [a-z0-9_.@-]+ is not active after deployment)/i
	);
	let reason = inactiveMatch ? (inactiveMatch[1] || inactiveMatch[2]) : '';
	if (!reason && errors.length) {
		reason = errors[errors.length - 1];
	}
	if (!reason) {
		reason = lines[lines.length - 1] || 'Unknown server error';
	}
	if (reason.length > 300) {
		reason = reason.substring(0, 297) + '...';
	}

	let summary = reason;
	if (/rollback status is (?:auto_)?rollback_failed|automatic rollback (?:also )?failed/i.test(normalized)) {
		summary = 'Deployment failed. Automatic rollback failed. Reason: ' + reason;
	} else if (/rollback status is (?:auto_)?rolled_back|restored automatically/i.test(normalized)) {
		summary = 'Deployment failed. The previous configuration was restored automatically. Reason: ' + reason;
	}
	return {raw: normalized, summary: summary, errors: errors, warnings: warnings};
}
function compactRoxywiMessages(messages, limit = 5) {
	const shown = messages.slice(0, limit).map(function (message) {
		return message.length > 400 ? message.substring(0, 397) + '...' : message;
	});
	if (messages.length > limit) {
		shown.push('... and ' + (messages.length - limit) + ' more message(s).');
	}
	return shown.join('\n');
}
$(document).ajaxError(function myErrorHandler(event, xhr, ajaxOptions, thrownError) {
	if (ajaxOptions && ajaxOptions.suppressGlobalError) {
		return;
	}
	if (xhr.status != 401 && xhr.status != 404) {
		let errorMessage = xhr.responseJSON && xhr.responseJSON.error;
		if (!errorMessage) {
			if (xhr.status === 0) {
				errorMessage = 'Cannot connect to the server';
			} else {
				errorMessage = thrownError || xhr.statusText || ('HTTP error ' + xhr.status);
			}
		}
		if (window.RoxywiUI && window.RoxywiUI.toastError) {
			window.RoxywiUI.toastError(errorMessage, {
				action: ajaxOptions && ajaxOptions.type ? ajaxOptions.type + ' ' + ajaxOptions.url : ''
			});
		} else {
			const parsedResponse = parseRoxywiResponse(errorMessage);
			toastr.clear();
			toastr.error(escapeHtml(parsedResponse.summary));
		}
	}
});
function showStats() {
	$.ajax({
		url: "/stats/view/" + $("#service").val() + "/" + $("#serv").val(),
		success: function (data) {
			if (data.indexOf('error:') != '-1' && data.indexOf('Internal error:') == '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Stats", "Stats", "/stats/" + $("#service").val() + "/" + $("#serv").val());
				wait();
			}
		}
	});
}
function openStats() {
	let serv = $("#serv option:selected").val();
	let service_url = $('#service').val();
	let url = "/stats/"+service_url+"/"+serv
	let win = window.open(url, '_blank');
	win.focus();
}
function openVersions() {
	let serv = $("#serv option:selected").val();
	let service_url = $('#service').val();
	let url = "/config/versions/"+service_url+"/"+serv
	let win = window.open(url,"_self");
	win.focus();
}
function clearAllAjaxFields() {
	$("#ajax").empty();
	$('.alert').remove();
	try {
		myCodeMirror.toTextArea();
	} catch (e) {
		console.log(e)
	}
	$("#saveconfig").remove();
	$("h4").remove();
	$("#ajax-compare").empty();
	$("#config").empty();
}
function showConfig() {
	let edit_section = '';
	let edit_section_uri = '';
	let service = $('#service').val();
	let config_file = $('#config_file_name').val()
	let config_file_name = encodeURI(config_file);
	if (service === 'nginx' || service === 'apache') {
		if (config_file === undefined || config_file === null) {
			config_file_name = cur_url[7]
			if (config_file_name === '') {
				toastr.warning('Select a config file first');
				return false;
			} else {
				showConfigFiles(true);
			}
		}
	}
	clearAllAjaxFields();

	if (service === 'haproxy') {
		edit_section = findGetParameter('section');
		if (edit_section != null) {
			edit_section_uri = '?section=' + edit_section;
		}
	}
	let json_data = {
		"serv": $("#serv").val(),
		"service": service,
		"config_file_name": config_file_name,
		"edit_section": edit_section
	}
	$.ajax({
		url: "/config/" + service + "/show",
		data: JSON.stringify(json_data),
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data.data);
				$.getScript(configShow);
				window.history.pushState("Show config", "Show config", "/config/" + service + "/" + $("#serv").val() + "/show/" + config_file_name + edit_section_uri);
			}
		}
	});
}
function showConfigFiles(not_redirect=false, config_file_name=null) {
	var service = $('#service').val();
	var server_ip = $("#serv").val();
	clearAllAjaxFields();
	$.ajax( {
		url: "/config/" + service + "/show-files",
		data: {
			serv: server_ip,
			service: service
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-config_file_name").html(data);
				if (config_file_name) {
					$('#config_file_name').val(config_file_name);
					$('#config_file_name').selectmenu('refresh');
				}
				if (findGetParameter('findInConfig') === null) {
					if (not_redirect) {
						window.history.pushState("Show config", "Show config", "/config/" + service + "/" + server_ip + "/show-files");
					}
				}
			}
		}
	} );
}
function showConfigFilesForEditing() {
	let service = $('#service').val();
	let server_ip = $("#serv").val();
	let config_file_name = findGetParameter('config_file_name')
	if (service === 'nginx' || service === 'apache') {
		$.ajax({
			url: "/config/" + service + "/" + server_ip + "/edit/" + config_file_name,
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					$("#ajax-config_file_name").html(data);
				}
			}
		});
	}
}
function showUploadConfig() {
	let service = $('#service').val();
	let configver = $('#configver').val();
	let serv = $("#serv").val()
	let jsonData = {
		"serv": serv,
		"configver": configver
	}
	$.ajax( {
		url: "/config/" + service + "/show",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "POST",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				$("#ajax").html(data.data);
				window.history.pushState("Show config", "Show config", "/config/versions/" + service + "/" + serv + "/" + configver);
				$.getScript(configShow);
			}
		}
	} );
}
function showListOfVersion(for_delver) {
	let cur_url = window.location.href.split('/').pop();
	let service = $('#service').val();
	let serv = $("#serv").val();
	let configver = cur_url;
	clearAllAjaxFields();
	$.ajax( {
		url: "/config/version/" + service + "/list",
		data: {
			serv: serv,
			configver: configver,
			for_delver: for_delver
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#config_version_div").html(data);
				$( "input[type=checkbox]" ).checkboxradio();
				window.history.pushState("Show config", "Show config", "/config/versions/" + service + "/" + serv);
			}
		}
	} );
}
function findGetParameter(parameterName) {
    let result = null,
        tmp = [];
    let items = location.search.substr(1).split("&");
    for (let index = 0; index < items.length; index++) {
        tmp = items[index].split("=");
        if (tmp[0] === parameterName) result = decodeURIComponent(tmp[1]);
    }
    return result;
}
$( function() {
	checkTheme();
	$('a').click(function(e) {
		try {
			var cur_path = window.location.pathname;
			var attr = $(this).attr('href');
			if (cur_path == '/install' || cur_path == '/runtimeapi') {
				if (typeof attr !== typeof undefined && attr !== false) {
					$('title').text($(this).attr('title'));
					history.pushState({}, '', $(this).attr('href'));
					if ($(this).attr('href').split('#')[0] && $(this).attr('href').split('#')[0] != cur_path) {
						window.history.go()
					}
				}
			}
		} catch (err) {
			console.log(err);
		}
	});
	toastr.options.closeButton = true;
	toastr.options.progressBar = true;
	toastr.options.positionClass = 'toast-bottom-full-width';
	toastr.options.timeOut = 25000;
	toastr.options.extendedTimeOut = 50000;
	$('#errorMess').click(function(){
		$('#error').remove();
	});
	$( "#serv" ).on('selectmenuchange',function()  {
		$("#show").css("pointer-events", "inherit");
		$("#show").css("cursor", "pointer");
	});
	if ($( "#serv option:selected" ).val() == "Choose server")  {
		$("#show").css("pointer-events", "none");
		$("#show").css("cursor", "not-allowed");
	}
	$( "#tabs" ).tabs();
	$( "select" ).not('#log-viewer-form select').selectmenu();

    $( "[title]" ).tooltip({
		"content": function(){
			return $(this).attr("data-help");
		},
		show: {"delay": 1000}
	});
	$( "input[type=submit], button" ).not('#log-viewer-form button, #overview-logs button').button();
	$( "input[type=checkbox]" ).not('#log-viewer-form input').checkboxradio();
	$( ".controlgroup" ).controlgroup();
	initializeAppNavigation();

	$('#auth').submit(function () {
		let next_url = findGetParameter('next');
		let json_data = {
			"login": $('#login').val(),
			"pass": $('#pass').val(),
			"next": next_url
		}
		$.ajax({
			url: "/login",
			data: JSON.stringify(json_data),
			contentType: "application/json; charset=utf-8",
			type: "POST",
			statusCode: {
				401: function (xhr) {
					$('.alert').show();
					if (xhr.responseText.indexOf('disabled') != '-1') {
						$('.alert').html('Your login is disabled')
					} else {
						$('.alert').html('Login or password is incorrect');
						ban();
					}
				}
			},
			success: function (data) {
				if (data.status === 'failed') {
					if (data.error.indexOf('disabled') != '-1') {
						$('.alert').show();
						$('.alert').html(data.error);
					} else {
						$('.alert').show();
						$('.alert').html(data.error);
						ban();
					}
				} else {
					sessionStorage.removeItem('check-service');
					window.location.replace(data.next_url);
				}
			}
		});
		return false;
	});
	let cur_url = window.location.href.split('/').pop();
	cur_url = cur_url.split('#');
	if (cur_url[0].indexOf('install') != '-1') {
		$(".installproxy").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'installproxy');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		$(".installmon").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'installmon');
			});
			$("#tabs").tabs("option", "active", 1);
		});
		$(".installgeo").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'installgeo');
			});
			$("#tabs").tabs("option", "active", 2);
		});
	}
	if (cur_url[0].indexOf('admin') != '-1') {
		$(".users").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'users');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		$(".servers").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'servers');
			});
			$("#tabs").tabs("option", "active", 1);
		});
		$(".ssh").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'ssh');
			});
			$("#tabs").tabs("option", "active", 2);
		});
		$(".settings").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'settings');
			});
			$("#tabs").tabs("option", "active", 3);
			loadSettings();
		});
		$(".backup").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'backup');
			});
			$("#tabs").tabs("option", "active", 4);
			loadBackup();
		});
		$(".groups").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'groups');
			});
			$("#tabs").tabs("option", "active", 5);
		});
		$(".tools").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'tools');
			});
			$("#tabs").tabs("option", "active", 6);
			loadServices();
		});
		$(".updatehapwi").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'updatehapwi');
			});
			$("#tabs").tabs("option", "active", 7);
			loadupdatehapwi();
		});
		$(".oidc").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'oidc');
			});
			$("#tabs").tabs("option", "active", 8);
		});
	}
	$('.copyToClipboard').hover(function (){
		$.getScript(overview);
	});
	$('.copyToClipboard').click(function () {
        let str = $(this).attr('data-copy');
        const el = document.createElement('textarea');
        el.value = str;
        el.setAttribute('readonly', '');
        el.style.position = 'absolute';
        el.style.left = '-9999px';
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
    })
});
function activeSubMenu(sub_menu, sub_menu_class) {
	sub_menu.find('a').removeClass('menu-active');
	let activeLink = sub_menu.children("." + sub_menu_class).get(0);
	if (activeLink) {
		activateNavigationLink(activeLink);
	}
}
function saveUserSettings(user_id){
	if ($('#disable_alerting').is(':checked')) {
		localStorage.removeItem('disabled_alert');
	} else {
		localStorage.setItem('disabled_alert', '1');
	}
	changeCurrentGroupF(user_id);
	changeTheme($('#theme_select').val());
	Cookies.set('lang', $('#lang_select').val(), { expires: 365, path: '/', secure: 'true' });
}
function sleep(ms) {
	return new Promise(resolve => setTimeout(resolve, ms));
}
function changeTheme(theme) {
	localStorage.setItem('theme', theme);
	if (theme === 'dark') {
		$('#menu-overview').children('img').attr('src', '/static/images/roxy_icon_white.png');
		$('#menu-haproxy').children('img').attr('src', '/static/images/HAProxy_icon_white.png');
		$('#menu-nginx').children('img').attr('src', '/static/images/NGINX_icon_white.png');
		$('#menu-keepalived').children('img').attr('src', '/static/images/keepalived_icon_white.png');
		$('.menu-logo').attr('src', '/static/images/logo_menu_white.png');
		$('head').append('<link rel="stylesheet" href="/static/css/dark.css" type="text/css" />');
	} else {
		$('#menu-overview').children('img').attr('src', '/static/images/roxy_icon.png');
		$('#menu-haproxy').children('img').attr('src', '/static/images/HAProxy_icon.png');
		$('#menu-nginx').children('img').attr('src', '/static/images/NGINX_icon.png');
		$('#menu-keepalived').children('img').attr('src', '/static/images/keepalived_icon.png');
		$('.menu-logo').attr('src', '/static/images/logo_menu.png');
		$('link[rel=stylesheet][href~="/static/css/dark.css"]').remove();
	}
}
function checkTheme() {
	let theme = localStorage.getItem('theme');
	changeTheme(theme);
}
function getRandomArbitrary(min, max) {
    return Math.random() * (max - min) + min;
}
async function ban() {
	$('#login').attr('disabled', 'disabled');
	$('#pass').attr('disabled', 'disabled');
	$("input[type=submit], button").button('disable');
	$('#wrong-login').show();
	$('#ban_10').show();
	$('#ban_timer').text(10);

	let i = 10;
	while (i > 0) {
		i--;
		await sleep(1000);
		$('#ban_timer').text(i);
	}

	$('#login').removeAttr('disabled');
	$('#pass').removeAttr('disabled');
	$("input[type=submit], button").button('enable');
	$('#ban_10').hide();
}
// function replace_text(id_textarea, text_var) {
// 	var str = $(id_textarea).val();
// 	var len = str.length;
// 	var len_var = text_var.length;
// 	var beg = str.indexOf(text_var);
// 	var end = beg + len_var
// 	var text_val = str.substring(0, beg) + str.substring(end, len);
// 	$(id_textarea).text(text_val);
// }

function initializeHistory() {
    if (!localStorage.getItem('history')) {
        localStorage.setItem('history', JSON.stringify(['/login', '/login', '/login']));
    }
}

function createHistory() {
    const history = JSON.parse(localStorage.getItem('history'));
    const currentPath = window.location.pathname.replace(/\/$/, "");
    const historyContainer = $('#browse_history');

    const removeDuplicates = (arr) => {
        const seen = {};
        return arr.filter(item => {
            const normalized = item.replace(/\/$/, "");
            return seen.hasOwnProperty(normalized) ? false : (seen[normalized] = true);
        });
    };

    if (!history.some(path => path.replace(/\/$/, "") === currentPath)) {
        let updatedHistory = [...history, currentPath];
        updatedHistory = removeDuplicates(updatedHistory);

        updatedHistory = updatedHistory.slice(-3);

        localStorage.setItem('history', JSON.stringify(updatedHistory));
    }

    historyContainer.empty();

    const menuLinks = {};
	
    $('.menu li ul li a').each(function() {
        const path = $(this).attr('href').replace(/\/$/, "");
        menuLinks[path] = {
            title: $(this).attr('title'),
            text: $(this).text()
        };
    });

    JSON.parse(localStorage.getItem('history')).forEach(path => {
        const cleanPath = path.replace(/\/$/, "");
        if (menuLinks[cleanPath]) {
            const link = menuLinks[cleanPath];
            historyContainer.append(
                `<li><a href="${cleanPath}" title="${link.title}">${link.text}</a></li>`
            );
        }
    });
}

$(document).ready(function() {
    initializeHistory();
    createHistory();
});

function changeCurrentGroupF(user_id) {
	$.ajax({
		url: "/user/" + user_id + "/groups/" + $('#newCurrentGroup').val(),
		contentType: "application/json; charset=utf-8",
		type: "PATCH",
		success: function (data) {
			if (data.error === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				location.reload();
			}
		}
	});
}
function updateTips( t ) {
	let tips = $( ".validateTips" );
	tips.text( t ).addClass( "alert-warning" );
	tips.text( t ).addClass( "alert-one-row" );
}
function clearTips() {
	let tips = $( ".validateTips" );
	tips.html('Fields marked "<span class="need-field">*</span>" are required').removeClass( "alert-warning" );
	let allFields = $( [] ).add( $('#new-server-add') ).add( $('#new-ip') ).add( $('#new-port')).add( $('#new-username') ).add( $('#new-password') )
	allFields.removeClass( "ui-state-error" );
}
function checkLength( o, n, min ) {
	if ( o.val().length < min ) {
		o.addClass( "ui-state-error" );
		updateTips("Field "+n+" is required");
		return false;
	} else {
		return true;
	}
}
$(function () {
	ion.sound({
		sounds: [
			{
				name: "bell_ring",
			},
			{
				name: "glass",
				volume: 1,
			},
			{
				name: "alert_sound",
				volume: 0.3,
				preload: false
			}
		],
		volume: 0.5,
		path: "/static/js/sounds/",
		preload: true
	});
});
const socketProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
let socket = new ReconnectingWebSocket(socketProtocol + window.location.host + '/socket', null, {maxReconnectAttempts: 20, reconnectInterval: 3000});

socket.onopen = async function(e) {
  console.log("[open] Connection is established with " + window.location.host);
  await authenticateSocket();
};

async function authenticateSocket() {
	try {
		const response = await fetch('/socket-ticket', {
			method: 'GET',
			credentials: 'same-origin',
			headers: {'Accept': 'application/json'}
		});
		if (!response.ok) {
			throw new Error(`ticket request failed with status ${response.status}`);
		}
		const ticket = await response.json();
		socket.send(JSON.stringify({type: 'authenticate', token: ticket.token}));
	} catch (error) {
		console.warn('[socket] Authentication failed:', error);
		socket.close(4003, 'Authentication failed');
	}
}

socket.onmessage = function(event) {
	var cur_url = window.location.href.split('/').pop();
	cur_url = cur_url.split('/');
	if (cur_url != 'login' && localStorage.getItem('disabled_alert') === null) {
		data = event.data.split(";");
		for (i = 0; i < data.length; i++) {
			if (data[i].indexOf('error:') != '-1' || data[i].indexOf('alert') != '-1' || data[i].indexOf('FAILED') != '-1') {
				if (data[i].indexOf('error: database is locked') == '-1') {
					toastr.error(data[i]);
					ion.sound.play("bell_ring");
				}
			} else if (data[i].indexOf('info: ') != '-1') {
				toastr.info(data[i]);
				ion.sound.play("glass");
			} else if (data[i].indexOf('success: ') != '-1') {
				toastr.success(data[i]);
				ion.sound.play("glass");
			} else if (data[i].indexOf('warning: ') != '-1') {
				toastr.warning(data[i]);
				ion.sound.play("bell_ring");
			} else if (data[i].indexOf('critical: ') != '-1') {
				toastr.error(data[i]);
				ion.sound.play("bell_ring");
			}
		}
	}
};

socket.onclose = function(event) {
  if (event.wasClean) {
    console.log(`[close] Соединение закрыто чисто, код=${event.code} причина=${event.reason}`);
  } else {
    console.log('[close] Соединение прервано');
  }
};

socket.onerror = function(error) {
  console.log(`[error] ${error.message}`);
};
function changePassword() {
	$("#user-change-password-table").dialog({
		autoOpen: true,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: "Change password",
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: [
			{
				text: $('#translate').attr('data-change'),
				click: function () {
					changeUserPasswordItOwn($(this));
				}
			}, {
				text: cancel_word,
				click: function () {
					$(this).dialog("close");
					$('#missmatchpass').hide();
				}
			}
		]
	});
}
function changeUserPasswordItOwn(d) {
	var pass = $('#change-password').val();
	var pass2 = $('#change2-password').val();
	if (pass != pass2) {
		$('#missmatchpass').show();
	} else {
		$('#missmatchpass').hide();
		toastr.clear();
		$.ajax({
			url: "/user/password",
			data: JSON.stringify({'pass': pass}),
			type: "POST",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					toastr.clear();
					d.dialog("close");
				}
			}
		});
	}
}
function findInConfig(words) {
	clearAllAjaxFields();
	$.ajax({
		url: "/config/" + $("#service").val() + "/find-in-config",
		data: {
			serv: $("#serv").val(),
			words: words
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
			}
		}
	});
}
function waitForElm(selector) {
	return new Promise(resolve => {
		if (document.querySelector(selector)) {
			return resolve(document.querySelector(selector));
		}

		const observer = new MutationObserver(mutations => {
			if (document.querySelector(selector)) {
				resolve(document.querySelector(selector));
				observer.disconnect();
			}
		});

		observer.observe(document.body, {
			childList: true,
			subtree: true
		});
	});
}
function randomIntFromInterval(min, max) {
  return Math.floor(Math.random() * (max - min + 1) + min)
}
function returnNiceCheckingConfig(data) {
	data = normalizeRoxywiResponse(data);
	if (data.indexOf('sudo: firewall-cmd: command not found') != '-1') {
		data = data.replaceAll('sudo: firewall-cmd: command not found\n', '');
		data = data.replaceAll('sudo: firewall-cmd: command not found', '');
		toastr.warning('The Firewalld service is not enabled. You should disable this setting for this server or enable the firewalld service on the server.')
	}
	data = data.replaceAll('Configuration file is valid', '');
	data = data.replaceAll('Warnings were found.', '');
	data = data.replaceAll('nginx: the configuration file /etc/nginx/nginx.conf syntax is ok', '');
	data = data.replaceAll('nginx: configuration file /etc/nginx/nginx.conf test is successful', '');
	data = data.replaceAll('Syntax OK', '');
	const parsedResponse = parseRoxywiResponse(data);
	const relevantWarnings = parsedResponse.warnings.filter(function (warning) {
		return warning.indexOf('global server state file') === -1;
	});
	if (parsedResponse.errors.length) {
		toastr.error('<pre style="padding: 0; margin: 0;">' + escapeHtml(
			compactRoxywiMessages(parsedResponse.errors)
		) + '</pre>');
		toastr.info('Config not applied');
		return 1;
	}
	if (relevantWarnings.length) {
		toastr.warning('<pre style="padding: 0; margin: 0;">' + escapeHtml(
			compactRoxywiMessages(relevantWarnings)
		) + '</pre>');
	}
	toastr.success('<b>Configuration file is valid</b>');
	return 0;
}
function loadVersion() {
	$.ajax({
		url: "/api/version",
		contentType: "application/json; charset=utf-8",
		success: function(data) {
			if (data.update_available) {
				$('#version').html('<span id="show-updates-button" class="new-version-exists" style="cursor: pointer;"></span>');
				$('#show-updates-button').text('v' + data.service_version);
			} else {
				$('#version').text('v' + data.service_version);
			}

			let showUpdates = $('#show-updates').dialog({
				autoOpen: false,
				width: 600,
				modal: true,
				title: 'There is a new Roxy-WI version',
				buttons: {
					Close: function() {
						$(this).dialog('close');
					}
				}
			});
			$('#show-updates-button').on('click', function() {
				showUpdates.dialog('open');
			});
		}
	});
}
function statAgriment() {
	var cur_url = window.location.href.split('/').pop();
	cur_url = cur_url.split('/');
	if (localStorage.getItem('statistic') == null && cur_url != 'login') {
		var titles = new Map()
		var body = new Map()
		var yes_ans = new Map()
		var no_ans = new Map()
		var ver_question = randomIntFromInterval(1, 2);
		titles.set(1, 'Help us improve Roxy-WI');
		titles.set(2, 'Data collection agreement');
		body.set(1, 'We want to improve the user experience by collecting anonymous statistics. No marketing.');
		body.set(2, 'We’d like to improve your experience in Roxy-WI, so we ask for statistics collection. No personal data is collected.');
		yes_ans.set(1, 'Yes');
		yes_ans.set(2, 'Agree and help the Roxy-WI team');
		no_ans.set(1, 'No');
		no_ans.set(2, 'Disagree');
		$("#statistic").dialog({
			autoOpen: true,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: titles.get(ver_question),
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: [{
				"id": "statYesBut",
				text: "Yes",
				click: function () {
					localStorage.setItem('statistic', '1');
					$(this).dialog("close");
					sendGet('page/ans/1/' + ver_question);
					statAgriment();
				},
			}, {
				"id": "statNoBut",
				text: "No",
				click: function () {
					localStorage.setItem('statistic', '0');
					$(this).dialog("close");
					sendGet('page/ans/0/' + ver_question);
				}
			}]
		});
		$("#statYesBut").html('<span class="ui-button-text">' + yes_ans.get(ver_question) + '</span>');
		$("#statNoBut").html('<span class="ui-button-text">' + no_ans.get(ver_question) + '</span>');
		$("#statistic-body").html(body.get(ver_question));
	}
	if (localStorage.getItem('statistic') == 1) {
		cur_url = btoa(cur_url);
		sendGet('/page/send/'+cur_url);
	}
}
function sendGet(page) {
	let xmlHttp = new XMLHttpRequest();
	let theUrl = 'https://roxy-wi.org/' + page;
	xmlHttp.open("GET", theUrl, true); // true for asynchronous
	xmlHttp.send(null);
}
function show_pretty_ansible_error(data) {
	try {
		data = data.split('error: ');
		let p_err = JSON.parse(data[1]);
		return p_err['msg'];
	} catch (e) {
		return data;
	}
}
function openTab(tabId) {
	$( "#tabs" ).tabs( "option", "active", tabId );
}
function showPassword(input, toggleButton) {
	let x = document.getElementById(input);
	if (!x) {
		return;
	}
	let showPassword = x.type === "password";
	x.type = showPassword ? "text" : "password";
	if (toggleButton) {
		let label = showPassword ? toggleButton.dataset.hideLabel : toggleButton.dataset.showLabel;
		toggleButton.setAttribute('aria-pressed', String(showPassword));
		toggleButton.setAttribute('aria-label', label);
		toggleButton.setAttribute('title', label);
		let showIcon = toggleButton.querySelector('.login-password-show-icon');
		let hideIcon = toggleButton.querySelector('.login-password-hide-icon');
		if (showIcon) showIcon.hidden = showPassword;
		if (hideIcon) hideIcon.hidden = !showPassword;
	}
}
function removeData() {
    for (let i = 0; i < charts.length; i++) {
        let chart = charts[i];
        chart.destroy();
    }
}
function common_ajax_action_after_success(dialog_id, new_group, ajax_append_id, data) {
	toastr.clear();
	$("#"+ajax_append_id).append(data);
	$( "."+new_group ).addClass( "update", 1000);
	$.getScript(awesome);
	clearTips();
	$( dialog_id ).dialog("close" );
	setTimeout(function() {
		$( "."+new_group ).removeClass( "update" );
	}, 2500 );
}
function getAllGroups() {
	let groups = '';
	$.ajax({
		url: "/server/groups",
		contentType: "application/json; charset=utf-8",
		async: false,
		success: function (data) {
			groups = data;
		}
	});
	return groups;
}
function openUserSettings(user_id) {
	if (localStorage.getItem('disabled_alert') === '1') {
		$('#disable_alerting').prop('checked', false).checkboxradio('refresh');
	} else {
		$('#disable_alerting').prop('checked', true).checkboxradio('refresh');
	}
	let theme = 'light';
	if (localStorage.getItem('theme') != null) {
		theme = localStorage.getItem('theme');
	}
	$('#theme_select').val(theme).change();
	$('#theme_select').selectmenu('refresh');
	$.ajax({
		url: "/user/group",
		success: function (data) {
			if (data.indexOf('danger') != '-1') {
				$("#ajax").html(data);
			} else {
				$('#show-user-settings-group').html(data);
				$("select").not('#log-viewer-form select').selectmenu();
			}
		}
	});
	let user_settings_tabel_title = $("#show-user-settings-table").attr('title');
	let change_pass_word = $('#translate').attr('data-change') + ' ' + $('#translate').attr('data-password')
	let showUserSettings = $("#show-user-settings").dialog({
		autoOpen: false,
		width: 600,
		modal: true,
		title: user_settings_tabel_title,
		buttons: [{
			text: save_word,
			click: function () {
				saveUserSettings(user_id);
				$(this).dialog("close");
			}
		}, {
			text: change_pass_word,
			click: function () {
				changePassword();
				$(this).dialog("close");
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
	showUserSettings.dialog('open');
}
function generateSelect(select_id, option_value, option_name, is_selected='') {
	$(select_id).append('<option value="' + option_value + '" '+is_selected+'>' + option_name + '</option>');
}
function makeid(length) {
   let result           = '';
   let characters       = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
   let charactersLength = characters.length;
   for ( let i = 0; i < length; i++ ) {
      result += characters.charAt(Math.floor(Math.random() * charactersLength));
   }
   return result;
}
const INSTALLATION_TASKS_KEY = 'installationTasks';
function getInstallationTasksFromSessionStorage() {
    const tasks = sessionStorage.getItem(INSTALLATION_TASKS_KEY);
    return tasks ? JSON.parse(tasks) : [];
}
function addItemToSessionStorageInstallTask(taskId) {
	if (!sessionStorage.getItem(INSTALLATION_TASKS_KEY)) {
		sessionStorage.setItem(INSTALLATION_TASKS_KEY, JSON.stringify([])); // Создаем пустой массив
	}
	let tasks = getInstallationTasksFromSessionStorage();

	tasks.push(taskId);

	sessionStorage.setItem(INSTALLATION_TASKS_KEY, JSON.stringify(tasks));
}
function removeItemFromSessionStorage(taskId) {
      let tasks = getInstallationTasksFromSessionStorage();

      tasks = tasks.filter(item => item !== taskId);

      sessionStorage.setItem(INSTALLATION_TASKS_KEY, JSON.stringify(tasks));
    }

function checkInstallationTask() {
	let tasks = getInstallationTasksFromSessionStorage(); // Извлекаем список
	if (tasks && tasks.length > 0) {
		tasks.forEach(item => {
			checkInstallationStatus(item);
		});
	} else {
		console.log('No tasks');
		clearInterval(checkInstallationTaskInterval);
	}
}
function runInstallationTaskCheck(tasks_ids) {
	toastr.info('Installation started. You can continue to use the system while it is installing');
	tasks_ids.forEach(item => {
		addItemToSessionStorageInstallTask(item);
		setTimeout(function () {
			setInterval(checkInstallationTask, 3000);
		}, 5000);
	});
}
function checkInstallationStatus(taskId) {
	NProgress.configure({showSpinner: false});
	$.ajax({
		url: "/install/task-status/" + taskId,
		success: function (data) {
			if (data.status === 'completed') {
				toastr.success('Installation completed for ' + data.service_name);
				removeItemFromSessionStorage(taskId);
			} else if (data.status === 'failed') {
				const serviceName = escapeHtml(String(data.service_name || 'service'));
				const operationError = escapeHtml(String(data.error || 'Unknown operations worker error'));
				toastr.error('Cannot install ' + serviceName + '. Error: ' + operationError);
				removeItemFromSessionStorage(taskId);
			}
		}
	});
	NProgress.configure({showSpinner: true});
}
let checkInstallationTaskInterval = setInterval(checkInstallationTask, 3000);
