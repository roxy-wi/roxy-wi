$( function() {
	$( "select" ).selectmenu({
	  width: 180
	});
	var ipformat = /^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
	$( "#interface" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					showif:1,
					serv: $("#master").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
						toastr.error(data);
					} else {
						response(data.split(" "));
					}
				}
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#interface-add" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					showif:1,
					serv: $("#master-add").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
						var p_err = show_pretty_ansible_error(data);
						toastr.error(p_err);
					} else {
						response(data.split(" "));
					}
				}
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#slave_interface" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					showif:1,
					serv: $("#slave").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
						var p_err = show_pretty_ansible_error(data);
						toastr.error(p_err);
					} else {
						response(data.split(" "));
					}
				}
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#slave_interface-add" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					showif:1,
					serv: $("#slave").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
						toastr.error(data);
					} else {
						response(data.split(" "));
					}
				}
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	var server_creating = $( "#server_creating" ).dialog({
		autoOpen: false,
		width: 574,
		modal: true,
		title: "Creating a new HA cluster",
		buttons: {
			Close: function() {
				$( this ).dialog( "close" );
				cleanProvisioningProccess('#server_creating ul li', '#created-mess', '#creating-error', '#creating-warning', '#creating-progress', '#creating-master', '#creating-slave', '#haproxy_installing_div', '#nginx_installing_div');
				$('#wait_mess').show();
			}
		}
	});
	var address_add = $( "#address_creating" ).dialog({
		autoOpen: false,
		width: 574,
		modal: true,
		title: "Adding a new VRRP address",
		buttons: {
			Close: function() {
				$( this ).dialog( "close" );
				cleanProvisioningProccess('#address_creating ul li', '#created-mess-add', '#creating-error', '#creating-warning-add', '#creating-progress-add', '#creating-master-add', '#creating-slave-add', '', '');
				$('#wait_mess-add').show();
			}
		}
	});
	$('#add-vrrp').click(function() {
		var kp = 0;
		if ($('#kp').is(':checked')) {
			kp = '1';
		} else {
			kp = '0';
		}
		$("#ajax").html('')
		if( $("#master-add").val() == "") {
			toastr.warning('Select a Master server');
		} else if($("#slave-add").val() == ""){
			toastr.warning('Select a Slave server');
		} else if($("#interface-add").val() == "") {
			toastr.warning('Please enter the master interface name')
		} else if ($("#vrrp-ip-add").val() == "") {
			toastr.warning('Please enter IP in "VRRP IP" field')
		} else if(! $("#vrrp-ip-add").val().match(ipformat)) {
			toastr.warning('Please enter IP in "VRRP IP" field')
		} else if($("#slave_interface-add") == '') {
			toastr.warning('Please enter the slave interface name')
		} else {
			$("#wait-mess-add").html(wait_mess);
			address_add.dialog('open');
			const router_id = randomIntFromInterval(1, 255);
			add_master_addr(kp, router_id);
			$.getScript("/inc/fontawesome.min.js");
			add_slave_addr(kp, router_id);
		}
	});
	$('#create').click(function() {
		var hap = 0;
		var nginx = 0;
		var syn_flood = 0;
		if ($('#hap').is(':checked')) {
			hap = '1';
		}
		if ($('#nginx').is(':checked')) {
			nginx = '1';
		}
		if ($('#syn_flood').is(':checked')) {
			syn_flood = '1';
		}
		$("#ajax").html('')
		if( $("#master").val() === null){
			toastr.warning('Select a Master server');
		} else if($("#slave").val() === null) {
			toastr.warning('Select a Slave server');
		} else if($("#interface").val() == "") {
			toastr.warning('Please enter the master interface name');
		} else if($("#vrrp-ip").val() == "") {
			toastr.warning('Please enter IP in "VRRP IP" field');
		} else if(! $("#vrrp-ip").val().match(ipformat)) {
			toastr.warning('Please enter IP in "VRRP IP" field');
		} else if($("#slave_interface").val() == '') {
			toastr.warning('Please enter the slave interface name');
		} else if ($("#master").val() == $("#slave").val() ){
			toastr.warning('Master and slave must be diff servers');
		} else {
				$("#wait-mess").html(wait_mess);
				server_creating.dialog('open');
				const router_id = randomIntFromInterval(1, 255);
				create_master_keepalived(hap, nginx, syn_flood, router_id);
				$.getScript("/inc/fontawesome.min.js");
				create_slave_keepalived(hap, nginx, syn_flood, router_id);
				if (hap == '1') {
					$('#haproxy_installing_div').show();
				}
				if (nginx == '1') {
					$('#nginx_installing_div').show();
				}
			}
	});
	$('#hap').click(function() {
		if ($('#hap').is(':checked')) {
			$('#haproxy_docker_td').show();
			$('#haproxy_docker_td_header').show();
		} else {
			$('#haproxy_docker_td').hide();
			$('#haproxy_docker_td_header').hide();
		}
	});
	$('#nginx').click(function() {
		if ($('#nginx').is(':checked')) {
			$('#nginx_docker_td').show();
			$('#nginx_docker_td_header').show();
		} else {
			$('#nginx_docker_td').hide();
			$('#nginx_docker_td_header').hide();
		}
	});
	$( "#master" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_keepalived_v: 1,
				serv: $('#master option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if(data.indexOf('keepalived:') != '-1') {
					$('#cur_master_ver').text('Keepalived has not installed');
					$('#create').attr('title', 'Create HA cluster');
				} else {
					$('#cur_master_ver').text(data);
					$('#cur_master_ver').css('font-weight', 'bold');
				}
			}
		} );
	});
	$( "#slave" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_keepalived_v: 1,
				serv: $('#slave option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if(data.indexOf('keepalived:') != '-1') {
					$('#cur_slave_ver').text('Keepalived has not installed');
					$('#create').attr('title', 'Create HA cluster');
				} else {
					$('#cur_slave_ver').text(data);
					$('#cur_slave_ver').css('font-weight', 'bold');
				}
			}
		} );
	});
	$( "#master-add" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_keepalived_v: 1,
				serv: $('#master-add option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if(data.indexOf('keepalived:') != '-1') {
					$('#cur_master_ver-add').text('Keepalived has not installed');
					$('#add-vrrp').attr('title', 'Add a HA configuration');
				} else {
					$('#cur_master_ver-add').text(data);
					$('#cur_master_ver-add').css('font-weight', 'bold');
				}
			}
		} );
	});
	$( "#slave-add" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_keepalived_v: 1,
				serv: $('#slave-add option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if(data.indexOf('keepalived:') != '-1') {
					$('#cur_slave_ver-add').text('Keepalived has not installed');
					$('#add-vrrp').attr('title', 'Add a HA configuration');
				} else {
					$('#cur_slave_ver-add').text(data);
					$('#cur_slave_ver-add').css('font-weight', 'bold');
				}
			}
		} );
	});
});
function add_master_addr(kp, router_id) {
	return_to_master = 0
	if ($('#add_return_to_master').is(':checked')) {
		return_to_master = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			masteradd: $('#master-add').val(),
			slaveadd: $('#slave-add').val(),
			interfaceadd: $("#interface-add").val(),
			slave_interfaceadd: $("#slave_interface-add").val(),
			vrrpipadd: $('#vrrp-ip-add').val(),
			return_to_master: return_to_master,
			kp: kp,
			router_id: router_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('UNREACHABLE') != '-1' || data.indexOf('FAILED') != '-1') {
				var p_err = show_pretty_ansible_error(data);
				showProvisioningError(p_err + '<br><br>', '#creating-master-add', '#wait-mess-add', '#creating-error-add');
			} else if (data == '' ){
				showProvisioningWarning('#creating-master-add', 'master Keepalived', '#creating-warning-add', '#wait_mess-add');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-master-add', '50', '#creating-progress-add', '#created-mess-add', '#wait-mess-add');
			}
		}
	} );
}
function add_slave_addr(kp, router_id) {
	$.ajax( {
		url: "options.py",
		data: {
			masteradd_slave: $('#master-add').val(),
			slaveadd: $('#slave-add').val(),
			interfaceadd: $("#interface-add").val(),
			slave_interfaceadd: $("#slave_interface-add").val(),
			vrrpipadd: $('#vrrp-ip-add').val(),
			kp: kp,
			router_id: router_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('UNREACHABLE') != '-1' || data.indexOf('FAILED') != '-1') {
				var p_err = show_pretty_ansible_error(data);
				showProvisioningError(p_err + '<br><br>', '#creating-slave-add', '#wait-mess-add', '#creating-error-add');
			} else if (data == '' ){
				showProvisioningWarning('#creating-slave-add', 'master Keepalived', '#creating-warning-add', '#wait_mess-add');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-slave-add', '100', '#creating-progress-add', '#created-mess-add', '#wait-mess-add');
			}
		}
	} );
}
function create_master_keepalived(hap, nginx, syn_flood, router_id) {
	if (hap == '0' && nginx == '0') {
		var progress_value = '50';
	} else if (hap == '1' || nginx == '0') {
		var progress_value = '43';
	} else if (hap == '1' && nginx == '1') {
		var progress_value = '50';
	}
	var virt_server = 0;
	var haproxy_docker = 0;
	var nginx_docker = 0;
	var return_to_master = 0;
	if ($('#virt_server').is(':checked')) {
		virt_server = '1';
	}
	if ($('#hap_docker').is(':checked')) {
		haproxy_docker = '1';
	}
	if ($('#nginx_docker').is(':checked')) {
		nginx_docker = '1';
	}
	if ($('#return_to_master').is(':checked')) {
		return_to_master = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			master: $('#master').val(),
			slave: $('#slave').val(),
			interface: $("#interface").val(),
			slave_interface: $("#slave_interface").val(),
			vrrpip: $('#vrrp-ip').val(),
			return_to_master: return_to_master,
			hap: hap,
			nginx: nginx,
			syn_flood: syn_flood,
			virt_server: virt_server,
			router_id: router_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
				var p_err = show_pretty_ansible_error(data);
				showProvisioningError(p_err + '<br><br>', '#creating-master', '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, 'master Keepalived', '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-master', progress_value, '#creating-progress', '#created-mess', '#wait-mess');
				$( "#master" ).trigger( "selectmenuchange" );
				if (hap === '1') {
					create_keep_alived_hap(nginx, 'master', haproxy_docker);
				}
				if (hap == '0' && nginx == '1') {
					create_keep_alived_nginx('master', nginx_docker);
				}
			} else {
				toastr.clear();
				toastr.info(data);
			}
		}
	} );
}
function create_slave_keepalived(hap, nginx, syn_flood, router_id) {
	if (hap == '0' && nginx == '0') {
		var progress_value = '100';
	} else if (hap == '1' || nginx == '0') {
		var progress_value = '67';
	} else if (hap == '1' && nginx == '1') {
		var progress_value = '50';
	}
	var haproxy_docker = 0;
	var nginx_docker = 0;
	if ($('#hap_docker').is(':checked')) {
		haproxy_docker = '1';
	}
	if ($('#nginx_docker').is(':checked')) {
		nginx_docker = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			master_slave: $('#master').val(),
			slave: $('#slave').val(),
			interface: $("#interface").val(),
			slave_interface: $("#slave_interface").val(),
			vrrpip: $('#vrrp-ip').val(),
			hap: hap,
			nginx: nginx,
			syn_flood: syn_flood,
			router_id: router_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
				var p_err = show_pretty_ansible_error(data);
				showProvisioningError(p_err + '<br><br>', '#creating-slave', '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, 'slave Keepalived', '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-slave', progress_value, '#creating-progress', '#created-mess', '#wait-mess');
				$( "#slave" ).trigger( "selectmenuchange" );
			} else {
				toastr.clear();
				toastr.info(data);
			}
			if (hap === '1') {
				create_keep_alived_hap(nginx, 'slave', haproxy_docker);
			}
			if (hap == '0' && nginx == '1') {
				create_keep_alived_nginx('slave', nginx_docker);
			}
		}
	} );
}
function create_keep_alived_hap(nginx, server, docker) {
	if (nginx == '0') {
		var progress_value = '100';
	} else if (nginx == '1') {
		var progress_value = '75';
	}
	if (server === 'master') {
		var step_id = '#creating-haproxy-master';
		var install_step = 'master Haproxy';
	} else {
		var step_id = '#creating-haproxy-slave';
		var install_step = 'slave Haproxy';
	}
	$(step_id).addClass('proccessing');
	$.ajax( {
		url: "options.py",
		data: {
			master_slave_hap: $('#master').val(),
			slave: $('#slave').val(),
			server: server,
			docker: docker,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
				var p_err = show_pretty_ansible_error(data);
				showProvisioningError(p_err + '<br><br>', step_id, '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, install_step, '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<br>'+data, step_id, progress_value, '#creating-progress', '#created-mess', '#wait-mess');
			} else {
				toastr.clear();
				toastr.info(data);
			}
			if (nginx == '1') {
				create_keep_alived_nginx(server, docker)
			}
		}
	} );
}
function create_keep_alived_nginx(server, docker) {
	if (server === 'master') {
		var step_id = '#creating-nginx-master';
		var install_step = 'master Nginx';
	} else {
		var step_id = '#creating-nginx-slave';
		var install_step = 'slave Nginx';
	}
	$(step_id).addClass('proccessing');
	$.ajax( {
		url: "options.py",
		data: {
			master_slave_nginx: $('#master').val(),
			slave: $('#slave').val(),
			server: server,
			docker: docker,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
				var p_err = show_pretty_ansible_error(data);
				showProvisioningError(p_err + '<br><br>', step_id, '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, install_step, '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<br>'+data, step_id, '100', '#creating-progress', '#created-mess', '#wait-mess');
			} else {
				toastr.clear();
				toastr.info(data);
			}
		}
	} );
}
function showProvisioningError(data, step_id, wait_mess, error_id) {
    $(wait_mess).hide();
    $(error_id).append(data);
	$(error_id).show();
	$(step_id).removeClass('proccessing');
	$(step_id).addClass('processing_error');
	$.getScript("/inc/fontawesome.min.js");
}
function showProvisioningWarning(step_id, install_step, warning_id, wait_id) {
    $(warning_id).append('<p>Something went wrong with installation on ' + install_step + ', check logs</p>');
    $(warning_id).show();
    $(step_id).removeClass('proccessing');
    $(step_id).addClass('processing_warning');
    $(wait_id).hide();
    $.getScript("/inc/fontawesome.min.js");
}
function cleanProvisioningProccess(div_id, success_div, error_id, warning_id, progres_id, keepalived_m_div, keepalived_s_div, haproxy_div, nginx_div) {
    $(success_div).empty();
    $(success_div).hide();
    $(error_id).empty();
    $(error_id).hide();
    $(warning_id).empty();
    $(warning_id).hide();
    $(progres_id).css('width', '0%');
    $(haproxy_div).hide();
	$(nginx_div).hide();
    $(div_id).each(function () {
        $(this).removeClass('proccessing_done');
        $(this).removeClass('processing_error');
        $(this).removeClass('processing_warning');
        $(this).removeClass('proccessing');
    });
	$(keepalived_m_div).addClass('proccessing');
	$(keepalived_s_div).addClass('proccessing');
    $.getScript("/inc/fontawesome.min.js");
}
function showProvisioningProccess(data, step_id, progress_value, progress_id, created_id, waid_id) {
    $(step_id).addClass('proccessing_done');
    $(step_id).removeClass('proccessing');
    $(created_id).show();
    $(created_id).append(data);
    $(progress_id).css('width', progress_value+'%');
    if (progress_value === '100')
    	$(waid_id).hide();
    $.getScript("/inc/fontawesome.min.js");
}
