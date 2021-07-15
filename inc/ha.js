$( function() {
	$( "select" ).selectmenu({
	  width: 180
	});
	var ipformat = /^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;

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
		if( $("#master-add").val() == "" || $("#slave-add").val() == "" || $("#interface-add").val() == "" ||
			$("#vrrp-ip-add").val() == "") {
				toastr.warning('Please fill in all fields')
			} else if(! $("#vrrp-ip-add").val().match(ipformat)) {
				toastr.warning('Please enter IP in "VRRP IP" field')
			} else {
				$("#wait-mess-add").html(wait_mess);
				address_add.dialog('open');
				add_master_addr(kp);
				$.getScript("/inc/fontawesome.min.js");
				add_slave_addr(kp);
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
		if( $("#master").val() == "" || $("#slave").val() == "" || $("#interface").val() == "" ||
			$("#vrrp-ip").val() == "") {
				toastr.warning('Please fill in all fields');
			} else if(! $("#vrrp-ip").val().match(ipformat)) {
				toastr.warning('Please enter IP in "VRRP IP" field');
			} else if ($("#master").val() == $("#slave").val() ){
				toastr.warning('Master and slave must be diff servers');
			} else {
				$("#wait-mess").html(wait_mess);
				server_creating.dialog('open');
				create_master_keepalived(hap, nginx, syn_flood);
				$.getScript("/inc/fontawesome.min.js");
				create_slave_keepalived(hap, nginx, syn_flood);
				if (hap == '1') {
					$('#haproxy_installing_div').show();
				}
				if (nginx == '1') {
					$('#nginx_installing_div').show();
				}
			}
	});
});
function add_master_addr(kp) {
	$.ajax( {
		url: "options.py",
		data: {
			masteradd: $('#master-add').val(),
			slaveadd: $('#slave-add').val(),
			interfaceadd: $("#interface-add").val(),
			vrrpipadd: $('#vrrp-ip-add').val(),
			kp: kp,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				showProvisioningError(data, '#creating-master-add', '#wait-mess-add', '#creating-error-add');
			} else if (data == '' ){
				showProvisioningWarning('#creating-master-add', 'master Keepalived', '#creating-warning-add', '#wait_mess-add');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-master-add', '50', '#creating-progress-add', '#created-mess-add', '#wait-mess-add');
			}
		}
	} );
}
function add_slave_addr(kp) {
	$.ajax( {
		url: "options.py",
		data: {
			masteradd_slave: $('#master-add').val(),
			slaveadd: $('#slave-add').val(),
			interfaceadd: $("#interface-add").val(),
			vrrpipadd: $('#vrrp-ip-add').val(),
			kp: kp,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				showProvisioningError(data, '#creating-slave-add', '#wait-mess-add', '#creating-error-add');
			} else if (data == '' ){
				showProvisioningWarning('#creating-slave-add', 'master Keepalived', '#creating-warning-add', '#wait_mess-add');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-slave-add', '100', '#creating-progress-add', '#created-mess-add', '#wait-mess-add');
			}
		}
	} );
}
function create_master_keepalived(hap, nginx, syn_flood) {
	if (hap == '0' && nginx == '0') {
		var progress_value = '50';
	} else if (hap == '1' || nginx == '0') {
		var progress_value = '43';
	} else if (hap == '1' && nginx == '1') {
		var progress_value = '50';
	}
	var virt_server = 0;
	if ($('#virt_server').is(':checked')) {
		virt_server = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			master: $('#master').val(),
			slave: $('#slave').val(),
			interface: $("#interface").val(),
			vrrpip: $('#vrrp-ip').val(),
			hap: hap,
			nginx: nginx,
			syn_flood: syn_flood,
			virt_server: virt_server,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1') {
				showProvisioningError(data, '#creating-master', '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, 'master Keepalived', '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-master', progress_value, '#creating-progress', '#created-mess', '#wait-mess');
				if (hap === '1') {
					create_keep_alived_hap(nginx, 'master');
				}
				if (hap == '0' && nginx == '1') {
					create_keep_alived_nginx('master');
				}
			} else {
				toastr.clear();
				toastr.info(data);
			}
		}
	} );
}
function create_slave_keepalived(hap, nginx, syn_flood) {
	if (hap == '0' && nginx == '0') {
		var progress_value = '100';
	} else if (hap == '1' || nginx == '0') {
		var progress_value = '67';
	} else if (hap == '1' && nginx == '1') {
		var progress_value = '50';
	}
	$.ajax( {
		url: "options.py",
		data: {
			master_slave: $('#master').val(),
			slave: $('#slave').val(),
			interface: $("#interface").val(),
			vrrpip: $('#vrrp-ip').val(),
			hap: hap,
			nginx: nginx,
			syn_flood: syn_flood,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1') {
				showProvisioningError(data, '#creating-slave', '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, 'slave Keepalived', '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<p>'+data+'</p>', '#creating-slave', progress_value, '#creating-progress', '#created-mess', '#wait-mess');
			} else {
				toastr.clear();
				toastr.info(data);
			}
			if (hap === '1') {
				create_keep_alived_hap(nginx, 'slave');
			}
			if (hap == '0' && nginx == '1') {
				create_keep_alived_nginx('slave');
			}
		}
	} );
}
function create_keep_alived_hap(nginx, server) {
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
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1') {
				showProvisioningError(data, step_id, '#wait-mess', '#creating-error');
			} else if (data == '' ){
				showProvisioningWarning(step_id, install_step, '#creating-warning', '#wait_mess');
			} else if (data.indexOf('success') != '-1' ){
				showProvisioningProccess('<br>'+data, step_id, progress_value, '#creating-progress', '#created-mess', '#wait-mess');
			} else {
				toastr.clear();
				toastr.info(data);
			}
			if (nginx == '1') {
				create_keep_alived_nginx(server)
			}
		}
	} );
}
function create_keep_alived_nginx(server) {
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
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1') {
				showProvisioningError(data, step_id, '#wait-mess', '#creating-error');
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
