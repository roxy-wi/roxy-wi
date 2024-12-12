window.onload = function() {
	var cur_url = window.location.href.split('/').pop();
	let activeTabIdx = $('#tabs').tabs('option','active');
	if (cur_url.split('#')[1] === 'ssl') {
		if (activeTabIdx === 4) {
			getLes();
		}
	}
}
$( function() {
	$("#tabs ul li").click(function () {
        let activeTab = $(this).find("a").attr("href");
        let activeTabClass = activeTab.replace('#', '');
        $('.menu li ul li').each(function () {
            activeSubMenu($(this), activeTabClass)
        });
        if (activeTab === '#ssl') {
            getLes();
        }
    });
	$("#listen-mode-select").on('selectmenuchange', function () {
		if ($("#listen-mode-select option:selected").val() === "tcp") {
			$("#https-listen-span").hide("fast");
			$("#https-hide-listen").hide("fast");
			$("#compression").checkboxradio("disable");
			$("#cache").checkboxradio("disable");
			$("#ssl_offloading").checkboxradio("disable");
			$("#listen_cookie").checkboxradio("disable");
			$("#slow_attack").checkboxradio("disable");
			$("#https-listen").prop("checked", false);
		} else {
			$("#https-listen-span").show("fast");
			$("#compression").checkboxradio("enable");
			$("#cache").checkboxradio("enable");
			$("#ssl_offloading").checkboxradio("enable");
			$("#listen_cookie").checkboxradio("enable");
			$("#slow_attack").checkboxradio("enable");
		}
	});
	$("#frontend-mode-select").on('selectmenuchange', function () {
		if ($("#frontend-mode-select option:selected").val() === "tcp") {
			$("#https-frontend-span").hide("fast");
			$("#https-hide-frontend").hide("fast");
			$("#compression2").checkboxradio("disable");
			$("#cache2").checkboxradio("disable");
			$("#ssl_offloading2").checkboxradio("disable");
			$("#slow_attack1").checkboxradio("disable");
		} else {
			$("#https-frontend-span").show("fast");
			$("#compression2").checkboxradio("enable");
			$("#cache2").checkboxradio("enable");
			$("#ssl_offloading2").checkboxradio("enable");
			$("#slow_attack1").checkboxradio("enable");
		}
	});
	$("#backend-mode-select").on('selectmenuchange', function () {
		if ($("#backend-mode-select option:selected").val() == "tcp") {
			$("#https-backend-span").hide("fast");
			$("#https-hide-backend").hide("fast");
			$("#compression3").checkboxradio("disable");
			$("#cache3").checkboxradio("disable");
			$("#ssl_offloading3").checkboxradio("disable");
			$("#backend_cookie").checkboxradio("disable");
			$("#slow_attack2").checkboxradio("disable");
		} else {
			$("#https-backend-span").show("fast");
			$("#compression3").checkboxradio("enable");
			$("#cache3").checkboxradio("enable");
			$("#ssl_offloading3").checkboxradio("enable");
			$("#backend_cookie").checkboxradio("enable");
			$("#slow_attack2").checkboxradio("enable");
		}
	});
	$("#controlgroup-listen-show").click(function () {
		if ($('#controlgroup-listen-show').is(':checked')) {
			$("#controlgroup-listen").show("fast");
			if ($('#check-servers-listen').is(':checked')) {
				$("#rise-listen").attr('required', true);
				$("#fall-listen").attr('required', true);
				$("#inter-listen").attr('required', true);
				$("#inter-listen").attr('disable', false);
			}
		} else {
			$("#controlgroup-listen").hide("fast");
		}
		$("#check-servers-listen").click(function () {
			if ($('#check-servers-listen').is(':checked')) {
				$("#rise-listen").attr('required', true);
				$("#fall-listen").attr('required', true);
				$("#inter-listen").attr('required', true);
				$("#inter-listen").selectmenu("option", "disabled", false);
				$("#fall-listen").selectmenu("option", "disabled", false);
				$("#rise-listen").selectmenu("option", "disabled", false);
			} else {
				$("#rise-listen").attr('required', false);
				$("#fall-listen").attr('required', false);
				$("#inter-listen").attr('required', false);
				$("#inter-listen").selectmenu("option", "disabled", true);
				$("#fall-listen").selectmenu("option", "disabled", true);
				$("#rise-listen").selectmenu("option", "disabled", true);
			}
		});
	});
	$("#controlgroup-backend-show").click(function () {
		if ($('#controlgroup-backend-show').is(':checked')) {
			$("#controlgroup-backend").show("fast");
			if ($('#check-servers-backend').is(':checked')) {
				$("#rise-backend").attr('required', true);
				$("#fall-backend").attr('required', true);
				$("#inter-backend").attr('required', true);
			}
		} else {
			$("#controlgroup-backend").hide("fast");
		}
	});
	$("#frontend_rewrite").on('selectmenuchange', function () {
		if ($("#frontend_rewrite option:selected").val() == "insert" || $("#frontend_rewrite option:selected").val() == "rewrite") {
			$("#frontend_prefix").checkboxradio("disable");
		} else {
			$("#frontend_prefix").checkboxradio("enable");
		}
	});
	$("#backend_rewrite").on('selectmenuchange', function () {
		if ($("#backend_rewrite option:selected").val() == "insert" || $("#backend_rewrite option:selected").val() == "rewrite") {
			$("#backend_prefix").checkboxradio("disable");
		} else {
			$("#backend_prefix").checkboxradio("enable");
		}
	});
	$("#check-servers-backend").click(function () {
		if ($('#check-servers-backend').is(':checked')) {
			$("#rise-backend").attr('required', true);
			$("#fall-backend").attr('required', true);
			$("#inter-backend").attr('required', true);
			$("#inter-backend").selectmenu("option", "disabled", false);
			$("#fall-backend").selectmenu("option", "disabled", false);
			$("#rise-backend").selectmenu("option", "disabled", false);
		} else {
			$("#rise-backend").attr('required', false);
			$("#fall-backend").attr('required', false);
			$("#inter-backend").attr('required', false);
			$("#inter-backend").selectmenu("option", "disabled", true);
			$("#fall-backend").selectmenu("option", "disabled", true);
			$("#rise-backend").selectmenu("option", "disabled", true);
		}
	});

	let availableTags = [
		"acl", "hdr(host)", "hdr_beg(host)", "hdr_dom(host)", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "set cookie", "dynamic-cookie-key", "mysql-check", "tcpka", "tcplog", "forwardfor", "option"
	];

	$("#ip").autocomplete({
		source: function (request, response) {
			if (!checkIsServerFiled('#serv')) return false;
			if (request.term == "") {
				request.term = 1
			}
			$.ajax({
				url: `/server/${$("#serv").val()}/ip`,
				contentType: "application/json; charset=utf-8",
				success: function (data) {
					response(data);
				}
			});
		},
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$('#listen-port').focus();
		}
	});
	$("#ip1").autocomplete({
		source: function (request, response) {
			if (!checkIsServerFiled('#serv2')) return false;
			if (request.term == "") {
				request.term = 1
			}
			$.ajax({
				url: `/server/${$("#serv2").val()}/ip`,
				contentType: "application/json; charset=utf-8",
				success: function (data) {
					response(data);
				}
			});
		},
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$('#frontend-port').focus();
		}
	});
	$("#backends").autocomplete({
		source: function (request, response) {
			if (!checkIsServerFiled('#serv2')) return false;
			if (request.term === "") {
				request.term = 1
			}
			$.ajax({
				url: "/runtimeapi/backends/" + $("#serv2").val(),
				success: function (data) {
					response(data.split('<br>'));
				}
			});
		},
		autoFocus: true,
		minLength: -1
	});
	$("#frontend_acl_then_value").autocomplete({
		source: function (request, response) {
			if ($('#frontend_acl_then').val() === '5') {
				if (!checkIsServerFiled('#serv2')) return false;
				if (request.term === "") {
					request.term = 1
				}
				$.ajax({
					url: "/runtimeapi/backends/" + $("#serv2").val(),
					success: function (data) {
						response(data.split('<br>'));
					}
				});
			} else {
				return false;
			}
		},
		autoFocus: true,
		minLength: -1
	});
	$("#new-option").autocomplete({
		source: availableTags,
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$("#new-option").append(ui.item.value + " ")
		}
	});
	$("#option_table input").change(function () {
		let id = $(this).attr('id').split('-');
		updateOptions(id[2])
	});
	$("#options").autocomplete({
		source: availableTags,
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$("#optionsInput").append(ui.item.value + " ");
			$(this).val('');
			return false;
		}
	});
	$("#saved-options").autocomplete({
		dataType: "json",
		source: "/add/option/get/" + $('#group_id').val(),
		autoFocus: true,
		minLength: 1,
		select: function (event, ui) {
			$("#optionsInput").append(ui.item.value + " \n");
			$(this).val('');
			return false;
		}
	});
	$("#options1").autocomplete({
		source: availableTags,
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$("#optionsInput1").append(ui.item.value + " ");
			$(this).val('');
			return false;
		}
	});
	$("#saved-options1").autocomplete({
		dataType: "json",
		source: "/add/option/get/" + $('#group_id').val(),
		autoFocus: true,
		minLength: 1,
		select: function (event, ui) {
			$("#optionsInput1").append(ui.item.value + " \n");
			$(this).val('');
			return false;
		}
	});
	$("#options2").autocomplete({
		source: availableTags,
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$("#optionsInput2").append(ui.item.value + " ");
			$(this).val('');
			return false;
		}
	});
	$("#saved-options2").autocomplete({
		dataType: "json",
		source: "/add/option/get/" + $('#group_id').val(),
		autoFocus: true,
		minLength: 1,
		select: function (event, ui) {
			$("#optionsInput2").append(ui.item.value + " \n");
			$(this).val('');
			return false;
		}
	});
	$('#add-option-button').click(function () {
		if ($('#option-add-table').css('display', 'none')) {
			$('#option-add-table').show("blind", "fast");
		}
	});
	$('#add-option-new').click(function () {
		$.ajax({
			url: "/add/option/save",
			data: {
				option: $('#new-option').val()
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					$("#option_table").append(data);
					setTimeout(function () {
						$(".newoption").removeClass("update");
					}, 2500);
					$.getScript(overview);
				}
			}
		});
	});
	$("#servers_table input").change(function () {
		let id = $(this).attr('id').split('-');
		updateSavedServer(id[2])

	});
	$('[name=servers]').autocomplete({
		source: "/add/server/get/" + $('#group_id').val(),
		autoFocus: true,
		minLength: 1,
		select: function (event, ui) {
			$(this).append(ui.item.value + " ");
			$(this).next().focus();
		}
	})
		.autocomplete("instance")._renderItem = function (ul, item) {
		return $("<li>")
			.append("<div>" + item.value + "<br>" + item.desc + "</div>")
			.appendTo(ul);
	};
	$('#add-saved-server-button').click(function () {
		if ($('#saved-server-add-table').css('display', 'none')) {
			$('#saved-server-add-table').show("blind", "fast");
		}
	});
	$('#add-saved-server-new').click(function () {
		$.ajax({
			url: "/add/server",
			data: JSON.stringify({
				server: $('#new-saved-servers').val(),
				description: $('#new-saved-servers-description').val()
			}),
			type: "POST",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data);
				} else {
					$("#servers_table").append(data.data);
					setTimeout(function () {
						$(".newsavedserver").removeClass("update");
					}, 2500);
					$.getScript(overview);
				}
			}
		});
	});
	$(":regex(id, template)").click(function () {
		if ($(':regex(id, template)').is(':checked')) {
			$(".prefix").show("fast");
			$(".second-server").hide("fast");
			$(".backend_server").hide("fast");
			$(".send_proxy").hide("fast");
			$("input[name=server_maxconn]").hide("fast");
			$("input[name=port_check]").hide("fast");
			$("[name=maxconn_name]").hide("fast");
			$("[name=port_check_text]").hide("fast");
			$(".prefix").attr('required', true);
		} else {
			$(".prefix").hide("fast");
			$(".prefix").attr('required', false);
			$(".second-server").show("fast");
			$(".backend_server").show("fast")
			$(".send_proxy").show("fast")
			$("input[name=server_maxconn]").show("fast");
			$("input[name=port_check]").show("fast");
			$("[name=maxconn_name]").show("fast");
			$("[name=port_check_text]").show("fast");
		}
	});
	let cur_url = window.location.href.split('/').pop();
	cur_url = cur_url.split('/');
	if (cur_url[0] == "add") {
		$("#cache").checkboxradio("disable");
		$("#waf").checkboxradio("disable");
		$("#serv").on('selectmenuchange', function () {
			change_select_acceleration("");
			change_select_waf("");
		});
		$("#cache2").checkboxradio("disable");
		$("#waf2").checkboxradio("disable");
		$("#serv2").on('selectmenuchange', function () {
			change_select_acceleration("2");
			change_select_waf("2");
		});
		$("#cache3").checkboxradio("disable");
		$("#serv3").on('selectmenuchange', function () {
			change_select_acceleration("3");
		});
		$('#compression').on("click", function () {
			if ($('#compression').is(':checked')) {
				$("#cache").checkboxradio("disable");
				$("#cache").prop('checked', false);
			} else {
				change_select_acceleration("");
			}
		});
		$('#compression2').on("click", function () {
			if ($('#compression2').is(':checked')) {
				$("#cache2").checkboxradio("disable");
				$("#cache2").prop('checked', false);
			} else {
				change_select_acceleration('2');
			}
		});
		$('#compression3').on("click", function () {
			if ($('#compression3').is(':checked')) {
				$("#cache3").checkboxradio("disable");
				$("#cache3").prop('checked', false);
			} else {
				change_select_acceleration('3');
			}
		});
		$('#cache').on("click", function () {
			if ($('#cache').is(':checked')) {
				$("#compression").checkboxradio("disable");
				$("#compression").prop('checked', false);
			} else {
				$("#compression").checkboxradio("enable");
			}
		});
		$('#cache2').on("click", function () {
			if ($('#cache2').is(':checked')) {
				$("#compression2").checkboxradio("disable");
				$("#compression2").prop('checked', false);
			} else {
				$("#compression2").checkboxradio("enable");
			}
		});
		$('#cache3').on("click", function () {
			if ($('#cache3').is(':checked')) {
				$("#compression3").checkboxradio("disable");
				$("#compression3").prop('checked', false);
			} else {
				$("#compression3").checkboxradio("enable");
			}
		});
		$("#add1").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children("#add1").css('padding-left', '30px');
				$(this).children("#add1").css('border-left', '4px solid #5D9CEB');
				$(this).children("#add1").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		$("#add3").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children("#add3").css('padding-left', '30px');
				$(this).children("#add3").css('border-left', '4px solid #5D9CEB');
				$(this).children("#add3").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			getLes();
			$("#tabs").tabs("option", "active", 4);
		});
		$("#add4").on("click", function () {
			$("#tabs").tabs("option", "active", 5);
		});
		$("#add5").on("click", function () {
			$("#tabs").tabs("option", "active", 6);
		});
		$("#add6").on("click", function () {
			$("#tabs").tabs("option", "active", 7);
			$("#userlist_serv").selectmenu("open");
		});
		$("#add7").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children("#add7").css('padding-left', '30px');
				$(this).children("#add7").css('border-left', '4px solid #5D9CEB');
				$(this).children("#add7").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			$("#tabs").tabs("option", "active", 9);
		});
	}
	$("#ssl_key_upload").click(function () {
		if (!checkIsServerFiled('#serv4')) return false;
		if (!checkIsServerFiled('#ssl_name', 'Enter the Certificate name')) return false;
		if (!checkIsServerFiled('#ssl_cert', 'Paste the contents of the certificate file')) return false;
		let jsonData = {
			server_ip: $('#serv4').val(),
			cert: $('#ssl_cert').val(),
			name: $('#ssl_name').val()
		}
		$.ajax({
			url: "/add/cert/add",
			data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			type: "POST",
			success: function (data) {
				if (data.error === 'failed') {
					toastr.error(data.error);
				} else {
					for (let i = 0; i < data.length; i++) {
						if (data[i]) {
							if (data[i].indexOf('error: ') != '-1' || data[i].indexOf('Errno') != '-1') {
								toastr.error(data[i]);
							} else {
								toastr.success(data[i]);
							}
						}
					}
				}
			}
		});
	});
	$('#ssl_key_view').click(function () {
		if (!checkIsServerFiled('#serv5')) return false;
		$.ajax({
			url: "/add/certs/" + $('#serv5').val(),
			success: function (data) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					let i;
					let new_data = "";
					data = data.split("\n");
					let j = 1
					for (i = 0; i < data.length; i++) {
						data[i] = data[i].replace(/\s+/g, ' ');
						if (data[i] != '') {
							if (j % 2) {
								if (j != 0) {
									new_data += '</span>'
								}
								new_data += '<span class="list_of_lists">'
							} else {
								new_data += '</span><span class="list_of_lists">'

							}
							j += 1
							new_data += ' <a onclick="view_ssl(\'' + data[i] + '\')" title="View ' + data[i] + ' cert">' + data[i] + '</a> '
						}
					}
					$("#ajax-show-ssl").html(new_data);
				}
			}
		});
	});
	$('[name=add-server-input]').click(function () {
		$("[name=add_servers]").append(add_server_var);
		changePortCheckFromServerPort();
	});
	$('[name=port]').on('input', function () {
		let iNum = parseInt($('[name=port]').val());
		$('[name=port_check]').val(iNum);
		$('[name=server_port]').val(iNum);
	});
	changePortCheckFromServerPort();
	$('#add-userlist-user').click(function () {
		$('#userlist-users').append(add_userlist_var);
	});
	$('#add-userlist-group').click(function () {
		$('#userlist-groups').append(add_userlist_group_var);
	});
	$('[name=add-peer-input]').click(function () {
		$("[name=add_peers]").append(add_peer_var);
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
	$(".redirectListen").on("click", function () {
		resetProxySettings();
		$("#tabs").tabs("option", "active", 1);
		$("#serv").selectmenu("open");
	});
	$(".redirectFrontend").on("click", function () {
		resetProxySettings();
		let TabId = 2;
		$("#tabs").tabs("option", "active", TabId);
		$("#serv" + TabId).selectmenu("open");
	});
	$(".redirectBackend").on("click", function () {
		resetProxySettings();
		let TabId = 3;
		$("#tabs").tabs("option", "active", TabId);
		$("#serv" + TabId).selectmenu("open");
	});
	$(".redirectSsl").on("click", function () {
		$("#tabs").tabs("option", "active", 4);
		$("#serv5").selectmenu("open");
	});
	let tcp_note = 'The check is valid when the server answers with a <b>SYN/ACK</b> packet'
	let ssl_note = 'The check is valid if the server answers with a valid SSL server <b>hello</b> message'
	let httpchk_note = 'The check is valid if the server answers with a status code of <b>2xx</b> or <b>3xx</b>. You can ' +
		'add a page for checking and Domain name'
	let ldap_note = 'The check is valid if the server response contains a successful <b>resultCode</b>.\n' +
		'<p>You must configure the LDAP servers according to this check to allow anonymous binding. ' +
		'You can do this with an IP alias on the server side that allows only HAProxy IP addresses to bind to it.</p>'
	let mysql_note = 'The check is valid if the server response contains a successful <b>Authentication</b> request'
	let pgsql_note = 'The check is valid if the server response contains a successful <b>Authentication</b> request'
	let redis_note = 'The check is valid if the server response contains the string <b>+PONG</b>'
	let smtpchk_note = 'The check is valid if the server response code starts with <b>\'2\'</b>'
	for (let section_type of ['listen', 'frontend']) {
		$("#" + section_type + "_blacklist-hide-input").autocomplete({
			source: function (request, response) {
				if (request.term === "") {
					request.term = 1
				}
				$.ajax({
					url: "/add/haproxy/bwlists/black/" + $("#group_id").val(),
					success: function (data) {
						data = data.replace(/\s+/g, ' ');
						response(data.split(" "));
					}
				});
			},
			autoFocus: true,
			minLength: -1
		});
		$("#" + section_type + "_whitelist-hide-input").autocomplete({
			source: function (request, response) {
				if (request.term == "") {
					request.term = 1
				}
				$.ajax({
					url: "/add/haproxy/bwlists/white/" + $("#group_id").val(),
					success: function (data) {
						data = data.replace(/\s+/g, ' ');
						response(data.split(" "));
					}
				});
			},
			autoFocus: true,
			minLength: -1
		});

		$("#" + section_type + "_blacklist_checkbox").click(function () {
			if ($("#" + section_type + "_blacklist_checkbox").is(':checked')) {
				$("#" + section_type + "_blacklist-hide").show("fast");
				$("#" + section_type + "_blacklist-hide-input").attr('required', true);
			} else {
				$("#" + section_type + "_blacklist-hide").hide("fast");
				$("#" + section_type + "_blacklist-hide-input").prop('required', false);
			}
		});

		$("#" + section_type + "_whitelist_checkbox").click(function () {
			if ($("#" + section_type + "_whitelist_checkbox").is(':checked')) {
				$("#" + section_type + "_whitelist-hide").show("fast");
				$("#" + section_type + "_whitelist-hide-input").attr('required', true);
			} else {
				$("#" + section_type + "_whitelist-hide").hide("fast");
				$("#" + section_type + "_whitelist-hide-input").prop('required', false);
			}
		});
		$("#path-cert-" + section_type).autocomplete({
			source: function (request, response) {
				let server = $("#add-" + section_type + " select[name='server'] option:selected");
				if (!checkIsServerFiled("#add-" + section_type + " select[name='server'] option:selected")) return false;
				$.ajax({
					url: "/add/certs/" + server.val(),
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
	for (let section_type of ['listen', 'backend']) {
		$("#" + section_type + "_checks").on('selectmenuchange', function () {
			let health_check_val = $("#" + section_type + "_checks").val();
			if (health_check_val === "tcp-check") {
				$("#" + section_type + "_checks_note").html(tcp_note)
			}
			if (health_check_val === "ssl-hello-chk") {
				$("#" + section_type + "_checks_note").html(ssl_note)
			}
			if (health_check_val === "httpchk") {
				$("#" + section_type + "_checks_note").html(httpchk_note);
				$("#" + section_type + "_checks_http").show();
				$("#" + section_type + "_checks_http_path").attr('required', 'true');
			} else {
				$("#" + section_type + "_checks_http").hide();
				$("#" + section_type + "_checks_http_path").removeAttr('required');
				$("#" + section_type + "_checks_http_domain").removeAttr('required');
			}
			if (health_check_val === "ldap-check") {
				$("#" + section_type + "_checks_note").html(ldap_note)
			}
			if (health_check_val === "mysql-check") {
				$("#" + section_type + "_checks_note").html(mysql_note)
			}
			if (health_check_val === "pgsql-check") {
				$("#" + section_type + "_checks_note").html(pgsql_note)
			}
			if (health_check_val === "redis-check") {
				$("#" + section_type + "_checks_note").html(redis_note)
			}
			if (health_check_val === "smtpchk") {
				$("#" + section_type + "_checks_note").html(smtpchk_note)
			}
			if (health_check_val === "") {
				$("#" + section_type + "_checks_note").html('')
			}
		});
		$("#ssl-dis-check-" + section_type).click(function () {
			if ($('#ssl-dis-check-' + section_type).is(':checked')) {
				$("#ssl-check-" + section_type).checkboxradio("disable");
				$("#ssl-check-" + section_type).prop("checked", false);
				$("#ssl-check-" + section_type).checkboxradio("refresh");
			} else {
				$("#ssl-check-" + section_type).checkboxradio("enable");
				$("#ssl-check-" + section_type).prop("checked", true);
				$("#ssl-check-" + section_type).checkboxradio("refresh");
			}
		});
		$("#" + section_type + "_circuit_breaking").click(function () {
			if ($("#" + section_type + "_circuit_breaking").is(':checked')) {
				$("#" + section_type + "_circuit_breaking_div").show("fast");
			} else {
				$("#" + section_type + "_circuit_breaking_div").hide("fast");
			}
		});
		$("#" + section_type + "_cookie").click(function () {
			if ($("#" + section_type + "_cookie").is(':checked')) {
				$("#" + section_type + "_cookie_name").attr('required', true);
				$("#" + section_type + "_cookie_div").show("fast");
			} else {
				$("#" + section_type + "_cookie_name").attr('required', false);
				$("#" + section_type + "_cookie_div").hide("fast");
				$("#" + section_type + "_dynamic-cookie-key").attr('required', false);
			}
		});
		$("#" + section_type + "_dynamic").click(function () {
			if ($("#" + section_type + "_dynamic").is(':checked')) {
				$("#" + section_type + "_dynamic-cookie-key").attr('required', true);
				$("#" + section_type + "_dynamic_div").show("slide", "fast");
			} else {
				$("#" + section_type + "_dynamic-cookie-key").attr('required', false);
				$("#" + section_type + "_dynamic_div").hide("slide", "fast");
			}
		});
	}
	for (let section_type of ['listen', 'frontend', 'backend']) {
		$("#add_" + section_type + "_header").on("click", function () {
			$("#" + section_type + "_header_div").show();
			$("#" + section_type + "_add_header").show();
			$("#add_" + section_type + "_header").hide();
		});
		$("#" + section_type + "_add_header").click(function () {
			make_actions_for_adding_header('#' + section_type + '_header_div');
		});
		$("#add_" + section_type + "_acl").on("click", function () {
			$("#" + section_type + "_acl").show();
			$("#" + section_type + "_add_acl").show();
			$("#add_" + section_type + "_acl").hide();
		});
		$("#" + section_type + "_add_acl").click(function () {
			make_actions_for_adding_acl_rule('#' + section_type + '_acl');
			if (section_type === 'listen') {
				$("#" + section_type + "_acl").find('option[value=5]').remove();
			}
		});
		$("#add_bind_" + section_type).click(function () {
			make_actions_for_adding_bind('#' + section_type + '_bind');
		});
		$("#https-" + section_type).click(function () {
			if ($('#https-' + section_type).is(':checked')) {
				$("#https-hide-" + section_type).show("fast");
				$("#path-cert-" + section_type).attr('required', true);
			} else {
				$("#https-hide-" + section_type).hide("fast");
				$("#path-cert-" + section_type).prop('required', false);
			}
		});
		$("#options-" + section_type + "-show").click(function () {
			if ($("#options-"+section_type+"-show").is(':checked')) {
				$("#options-" + section_type + "-show-div").show("fast");
			} else {
				$("#options-" + section_type + "-show-div").hide("fast");
			}
		});
		let tableId = 3;
		if (section_type === 'listen') {
			tableId = 1;
		} else if (section_type === 'frontend') {
			tableId = 2
		}
		$("#create-http-" + section_type).on("click", function () {
			resetProxySettings();
			createHttp(tableId, section_type);
		});
		$("#create-ssl-" + section_type).on("click", function () {
			resetProxySettings();
			createSsl(tableId, section_type);
		});
		$("#create-https-" + section_type).on("click", function () {
			resetProxySettings();
			createHttps(tableId, section_type);
		});
	}
	$("#serv").on('selectmenuchange', function () {
		$('#name').focus();
	});
	$("#serv2").on('selectmenuchange', function () {
		$('#new_frontend').focus();
	});
	$("#serv3").on('selectmenuchange', function () {
		$('#new_backend').focus();
	});
	$("#userlist_serv").on('selectmenuchange', function () {
		$('#new_userlist').focus();
	});
});
function resetProxySettings() {
	$('[name=ip]').val('');
	$('[name=port]').val('');
	$('[name=server_port]').val('');
	$('input:checkbox').prop( "checked", false );
	$('[name=ssl-check]').prop( "checked", true );
	$('[name=ssl-dis-check]').prop( "checked", false );
	$('[name=check-servers]').prop( "checked", true );
	$('input:checkbox').checkboxradio("refresh");
	$('.advance-show').fadeIn();
	$('.advance').fadeOut();
	$('[id^=https-hide]').hide();
	$('[name=mode]').val('http');
	$('select').selectmenu('refresh');
	$("#path-cert-listen" ).attr('required',false);
	$("#path-cert-frontend" ).attr('required',false);
}
function createHttp(TabId, proxy) {
	$('[name=port]').val('80');
	$('[name=server_port]').val('80');
	$( "#tabs" ).tabs( "option", "active", TabId );
	if (TabId == 1) {
		TabId = '';
	}
	$( "#serv"+TabId ).selectmenu( "open" );
	history.pushState('Add '+proxy, 'Add '+proxy, '#'+proxy)
}
function createSsl(TabId, proxy) {
	$('[name=port]').val('443');
	$('[name=server_port]').val('80');
	$('.advance-show').fadeOut();
	$('.advance').fadeIn()
	$( "#tabs" ).tabs( "option", "active", TabId );
	$( "#https-hide-"+proxy).show("fast");
	$('#https-'+proxy).prop( "checked", true );
	$('#ssl-dis-check-'+proxy).prop( "checked", true );
	$('#ssl-check-'+proxy).prop( "checked", false );
	$('#ssl-check-'+proxy).checkboxradio('disable');
	$('input:checkbox').checkboxradio("refresh");
	$("#path-cert-"+proxy ).attr('required',true);
	if (TabId == 1) {
		TabId = '';
	}
	$( "#serv"+TabId ).selectmenu( "open" );
	history.pushState('Add'+proxy, 'Add'+proxy, 'haproxy#'+proxy)
}
function createHttps(TabId, proxy) {
	$('[name=port]').val('443');
	$('[name=server_port]').val('443');
	$('.advance-show').fadeOut();
	$('.advance').fadeIn();
	$( "#tabs" ).tabs( "option", "active", TabId );
	$('#'+proxy+'-mode-select').val('tcp');
	$('#'+proxy+'-mode-select').selectmenu('refresh');
	if (TabId == 1) {
		TabId = '';
	}
	$( "#serv"+TabId ).selectmenu( "open" );
	history.pushState('Add'+proxy, 'Add'+proxy, 'haproxy#'+proxy)
}
function confirmDeleteOption(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#option-body-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeOption(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function removeOption(id) {
	$("#option-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "/add/option/delete/" + id,
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#option-"+id).remove();
			}
		}
	} );
}
function updateOptions(id) {
	toastr.clear();
	$.ajax({
		url: "/add/option/update",
		data: {
			option: $('#option-body-' + id).val(),
			id: id,
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#option-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#option-" + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function confirmDeleteSavedServer(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#servers-ip-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeSavedServer(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function removeSavedServer(id) {
	$("#servers-saved-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/add/server/" + id,
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#servers-saved-" + id).remove();
			},
			404: function (xhr) {
				$("#servers-saved-" + id).remove();
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === "failed") {
					toastr.error(data);
				}
			}
		}
	});
}
function updateSavedServer(id) {
	toastr.clear();
	$.ajax( {
		url: "/add/server/" + id,
		type: "PUT",
		data: JSON.stringify({"server": $('#servers-ip-'+id).val(), description: $('#servers-desc-'+id).val(),}),
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				$("#servers-saved-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#servers-saved-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function view_ssl(id) {
	let raw_word = translate_div.attr('data-raw');
	if(!checkIsServerFiled('#serv5')) return false;
	$.ajax( {
		url: "/add/cert/" + $('#serv5').val() + '/' + id,
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$( "#dialog-confirm-cert" ).dialog({
					resizable: false,
					height: "auto",
					width: 670,
					modal: true,
					title: "Certificate from "+$('#serv5').val()+", name: "+id,
					buttons: [{
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}, {
						text: raw_word,
						click: function () {
							showRawSSL(id);
						}
					}, {
						text: delete_word,
						click: function () {
							$(this).dialog("close");
							confirmDeleting("SSL cert", id, $(this), "");
						}
					}]
				});
			}
		}
	} );
}
function showRawSSL(id) {
	$.ajax({
		url: "/add/cert/get/raw/" + $('#serv5').val() + "/" + id,
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$("#dialog-confirm-cert").dialog({
					resizable: false,
					height: "auto",
					width: 670,
					modal: true,
					title: "Certificate from " + $('#serv5').val() + ", name: " + id,
					buttons: [{
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}, {
						text: "Human readable",
						click: function () {
							view_ssl(id);
						}
					}, {
						text: delete_word,
						click: function () {
							$(this).dialog("close");
							confirmDeleting("SSL cert", id, $(this), "");
						}
					}]
				});
			}
		}
	});
}
function deleteSsl(id) {
	if (!checkIsServerFiled('#serv5')) return false;
	$.ajax({
		url: "/add/cert/" + $("#serv5").val() + "/" + id,
		type: "DELETE",
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				toastr.success('SSL cert ' + id + ' has been deleted');
				$("#ssl_key_view").trigger("click");
			}
		}
	});
}
function change_select_acceleration(id) {
	$.ajax({
		url: "/service/haproxy/" + $('#serv' + id + ' option:selected').val() + "/status",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (parseFloat(data.Version.split('-')[0]) < parseFloat('1.8') || data.Version == ' ') {
				$("#cache" + id).checkboxradio("disable");
			} else {
				$("#cache" + id).checkboxradio("enable");
			}
		}
	});
}
function change_select_waf(id) {
	$.ajax({
		url: "/service/haproxy/" + $('#serv' + id + ' option:selected').val() + "/status",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (parseFloat(data.Version.split('-')[0]) < parseFloat('1.8') || data.Version == ' ') {
				$("#waf" + id).checkboxradio("disable");
			} else {
				$("#waf" + id).checkboxradio("enable");
			}
		}
	});
}
function createList(color) {
	let list = $('#new_blacklist_name').val()
	if (color === 'white') {
		list = $('#new_whitelist_name').val()
	}
	let jsonData = {
		'name': escapeHtml(list),
		'color': color
	}
	$.ajax({
		url: "/add/haproxy/list",
		data: JSON.stringify(jsonData),
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				toastr.success('List has been created');
				setTimeout(function () {
					location.reload();
				}, 2500);
			}
		}
	});
}
function editList(list, color) {
	$.ajax( {
		url: "/add/haproxy/list/" + list + "/" + color,
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				$('#edit_lists').text(data.data.replaceAll('\n', '\r\n'));
				$( "#dialog-confirm-cert-edit" ).dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: edit_word + " "+list,
					buttons: [{
						text: delete_word,
						click: function () {
							$(this).dialog("close");
							confirmDeleting('list', list, $(this), color);
						}
					}, {
						text: just_save_word,
						click: function () {
							$(this).dialog("close");
							saveList('save', list, color);
						}
					}, {
						text: upload_and_reload,
						click: function () {
							$(this).dialog("close");
							saveList('reload', list, color);
						}
					}, {
						text: upload_and_restart,
						click: function () {
							$(this).dialog("close");
							saveList('restart', list, color);
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
	} );
}
function saveList(action, list, color) {
	let serv = $("#serv-" + color + "-list option:selected").val();
	if (!checkIsServerFiled($("#serv-" + color + "-list"))) return false;
	let jsonData = {
		name: list,
		server_ip: serv,
		content: $('#edit_lists').val(),
		color: color,
		action: action
	}
	$.ajax({
		url: "/add/haproxy/list",
		data: JSON.stringify(jsonData),
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error)
			} else {
				data = data.data.split(" , ");
				for (i = 0; i < data.length; i++) {
					if (data[i]) {
						if (data[i].indexOf('error: ') != '-1' || data[i].indexOf('Errno') != '-1') {
							toastr.error(data[i]);
						} else {
							if (data[i] != '\n') {
								toastr.success(data[i]);
							}
						}
					}
				}
			}
		}
	});
}
function deleteList(list, color) {
	let serv = $( "#serv-"+color+"-list option:selected" ).val();
	if(!checkIsServerFiled($("#serv-"+color+"-list"))) return false;
	let jsonData = {
		'name': list,
        'color': color,
		'server_ip': serv
	}
	$.ajax({
		url: "/add/haproxy/list",
		type: "DELETE",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				toastr.clear();
				toastr.success('List has been deleted');
				setTimeout(function () {location.reload();}, 2500);
			},
			404: function (xhr) {
				toastr.clear();
				toastr.success('List has been deleted');
				setTimeout(function () {location.reload();}, 2500);
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === 'failed') {
					toastr.error(data);
				}
			}
		}
	});
}
function createMap() {
	let map_name = $('#new_map_name').val()
	map_name = escapeHtml(map_name);
	$.ajax( {
		url: "/add/map",
		data: {
			map_name: map_name
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1' || data.indexOf('Errno') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('Info') != '-1' ){
				toastr.clear();
				toastr.info(data);
			} else if (data.indexOf('success') != '-1' ) {
				toastr.clear();
				toastr.success('A map has been created');
				setTimeout(function () {
					location.reload();
				}, 2500);
			}
		}
	} );
}
function editMap(map) {
	$.ajax({
		url: "/add/map",
		data: {
			map_name: map,
		},
		type: "GET",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#edit_map').text(data);
				$("#dialog-confirm-map-edit").dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: edit_word + " " + map,
					buttons: [{
						text: delete_word,
						click: function () {
							$(this).dialog("close");
							confirmDeleting('map', map, $(this));
						}
					}, {
						text: just_save_word,
						click: function () {
							$(this).dialog("close");
							saveMap('save', map);
						}
					}, {
						text: upload_and_reload,
						click: function () {
							$(this).dialog("close");
							saveMap('reload', map);
						}
					}, {
						text: upload_and_restart,
						click: function () {
							$(this).dialog("close");
							saveMap('restart', map);
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
function saveMap(action, map) {
	let serv = $( "#serv-map option:selected" ).val();
	if(!checkIsServerFiled($("#serv-map"))) return false;
	$.ajax({
		url: "/add/map",
		data: {
			map_name: map,
			serv: serv,
			content: $('#edit_map').val(),
			map_restart: action
		},
		type: "PUT",
		success: function (data) {
			data = data.split(" , ");
			for (i = 0; i < data.length; i++) {
				if (data[i]) {
					if (data[i].indexOf('error: ') != '-1' || data[i].indexOf('Errno') != '-1') {
						toastr.error(data[i]);
					} else {
						if (data[i] != '\n') {
							toastr.success(data[i]);
						}
					}
				}
			}
		}
	});
}
function deleteMap(map) {
	let serv = $( "#serv-map option:selected" ).val();
	if(!checkIsServerFiled($("#serv-map"))) return false;
	$.ajax({
		url: "/add/map",
		data: {
			map_name: map,
			serv: serv,
		},
		type: "DELETE",
		success: function (data) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1' || data.indexOf('Errno') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('Info') != '-1' ){
				toastr.clear();
				toastr.info(data);
			} else if (data.indexOf('success') != '-1' ) {
				toastr.clear();
				toastr.success('The map has been deleted');
				setTimeout(function () {location.reload();}, 2500);
			}
		}
	});
}
function confirmDeleting(deleting_thing, id, dialog_id, color) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + deleting_thing + " " +id + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				if (deleting_thing == "SSL cert") {
					deleteSsl(id);
					$(dialog_id).dialog("close");
				} else if (deleting_thing == "list") {
					deleteList(id, color);
					$(dialog_id).dialog("close");
				} else if (deleting_thing == "map") {
					deleteMap(id);
					$(dialog_id).dialog("close");
				}
				$(this).dialog("close");
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
				$(dialog_id).dialog( "open" );
			}
		}]
	});
}
function deleteId(id) {
	$('#' + id).remove();
	if ($('#listen_bind > p').length == 0) {
		$('#listen_bind').hide();
	}
	if ($('#frontend_bind > p').length == 0) {
		$('#frontend_bind').hide();
	}
	if ($('#backend_bind > p').length == 0) {
		$('#backend_bind').hide();
	}
}
var if_word = translate_div.attr('data-if-title');
var then_word = translate_div.attr('data-then');
var value_word = translate_div.attr('data-value');
var name_word = translate_div.attr('data-name');
var acl_option = '<p id="new_acl_p" style="border-bottom: 1px solid #ddd; padding-bottom: 10px;">\n' +
		'<b class="padding10">'+if_word+'</b>\n' +
		'<select name="acl_if">\n' +
		'\t<option selected>Select if</option>\n' +
		'\t<option value="1">Host name starts with</option>\n' +
		'\t<option value="2">Host name ends with</option>\n' +
		'\t<option value="3">Path starts with</option>\n' +
		'\t<option value="4">Path ends with</option>\n' +
		'\t<option value="6">Src ip</option>\n' +
		'</select> ' +
		'<b class="padding10">'+value_word+'</b>\n' +
		'<input type="text" name="acl_value" class="form-control">\n' +
		'<b class="padding10">'+then_word+'</b>\n' +
		'<select name="acl_then">\n' +
		'\t<option selected>Select then</option>\n' +
		'\t<option value="5">Use backend</option>\n' +
		'\t<option value="2">Redirect to</option>\n' +
		'\t<option value="3">Allow</option>\n' +
		'\t<option value="4">Deny</option>\n' +
		'\t<option value="6">Return</option>\n' +
		'\t<option value="7">Set-header</option>\n' +
		'</select>\n' +
		'<b class="padding10">'+value_word+'</b>\n' +
		'<input type="text" name="acl_then_value" class="form-control" value="" title="Required if\" then\" is \"Use backend\" or \"Redirect\"">\n' +
		'<span class="minus minus-style" id="new_acl_rule_minus" title="Delete this ACL"></span>' +
		'</p>'
function make_actions_for_adding_acl_rule(section_id) {
	let random_id = makeid(3);
	$(section_id).append(acl_option);
	$('#new_acl_rule_minus').attr('onclick', 'deleteId(\''+random_id+'\')');
	$('#new_acl_rule_minus').attr('id', '');
	$('#new_acl_p').attr('id', random_id);
	$('#new_acl_rule_minus').attr('id', '');
	$.getScript(awesome);
	$( "select" ).selectmenu();
	$('[name=acl_if]').selectmenu({width: 180});
	$('[name=acl_then]').selectmenu({width: 180});
}
var header_option = '<p style="border-bottom: 1px solid #ddd; padding-bottom: 10px;" id="new_header_p">\n' +
	'<select name="headers_res">' +
	'<option value="http-response">response</option>' +
	'<option value="http-request">request</option>' +
	'</select>' +
	'<select name="headers_method">' +
	'<option value="add-header">add-header</option>' +
	'<option value="set-header">set-header</option>' +
	'<option value="del-header">del-header</option>' +
	'</select>' +
	'\t<b class="padding10">'+name_word+'</b>' +
	'\t<input name="header_name" class="form-control">' +
	'\t<b class="padding10">'+value_word+'</b>' +
	'\t<input name="header_value" class="form-control" placeholder="Leave blank if using del-header">' +
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
var bind_option = '<p id="new_bind_p"><input type="text" name="ip" size="15" placeholder="Any" class="form-control ui-autocomplete-input" autocomplete="off">' +
	'<b>:</b> ' +
	'<input type="text" name="port" size="5" style="" required="" placeholder="8080" title="Port for bind listen" class="form-control" autocomplete="off"> ' +
	'<span class="minus minus-style" id="new_bind_minus" title="Remove the IP-port pair"></span>'
function make_actions_for_adding_bind(section_id) {
	let random_id = makeid(3);
	$(section_id).append(bind_option);
	$('#new_bind_minus').attr('onclick', 'deleteId(\''+random_id+'\')');
	$('#new_bind_minus').attr('id', '');
	$('#new_bind_p').attr('id', random_id);
	$('#new_bind_minus').attr('id', '');
	$.getScript(awesome);
	$( "select" ).selectmenu();
	let serv = 'serv2'
	if(section_id == '#listen_bind') {
		serv = 'serv'
	}
	$( "#"+random_id + " > input[name=ip]").autocomplete({
		source: function (request, response) {
			if (request.term == "") {
				request.term = 1
			}
			$.ajax({
				url: "/server/" + $("#" + serv).val() + "/ip",
				contentType: "application/json; charset=utf-8",
				success: function (data) {
					response(data);
				}
			});
		},
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$("#" + random_id + " > input[name=port]").focus();
		}
	});
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
function changePortCheckFromServerPort() {
	$('[name=server_port]').on('input', function () {
		let iNum = parseInt($($(this)).val());
		$($(this)).next().val(iNum);
	});
}
