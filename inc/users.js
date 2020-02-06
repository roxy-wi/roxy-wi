var awesome = "/inc/fontawesome.min.js"

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

$( function() {
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
					response(data.split(" "));
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
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	var ipformat = /^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
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
				$("#ajax").html('<div class="alert alert-danger">Please fill in all fields</div>')
			} else if(! $("#vrrp-ip").val().match(ipformat)) {
				$("#ajax").html('<div class="alert alert-danger">Please enter IP in "VRRP IP" field</div>')
			} else if ($("#master").val() == $("#slave").val() ){
				$("#ajax").html('<div class="alert alert-danger">Master and slave must be diff servers</div>')
			} else {
				$("#ajax").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
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
						token: $('#token').val()
					},
					type: "POST",
					success: function( data ) { 
						data = data.replace(/\s+/g,' ');
						if (data.indexOf('error') != '-1' || data.indexOf('alert') != '-1' || data.indexOf('FAILED') != '-1') {
							$("#ajax").html('<div class="alert alert-danger">'+data+'</div>');
						} else if (data.indexOf('info') != '-1' ){
							$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
						} else if (data.indexOf('success') != '-1' ){
							$('.alert-danger').remove();
							$("#ajax").html('<div class="alert alert-success">'+data+'</div>');				
						} else {
							$('.alert-danger').remove();
							$('.alert-warning').remove();
							$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
						}
					}
				} );
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
				$("#ajax").html('<div class="alert alert-danger">Please fill in all fields</div>')
			} else if(! $("#vrrp-ip-add").val().match(ipformat)) {
				$("#ajax").html('<div class="alert alert-danger">Please enter IP in "VRRP IP" field</div>')
			} else {
				$("#ajax").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
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
						if (data.indexOf('error') != '-1') {
							$("#ajax").html('<div class="alert alert-danger">'+data+'</div>');
						} else if (data.indexOf('success') != '-1'){
							$('.alert-danger').remove();
							$("#ajax").html('<div class="alert alert-success">'+data+'</div>');				
						} else {
							$('.alert-danger').remove();
							$('.alert-warning').remove();
							$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
						}
					}
				} );
			}
	});
	$('#install').click(function() {
		$("#ajax").html('')
		var syn_flood = 0;
		if ($('#syn_flood').is(':checked')) {
			syn_flood = '1';
		}
		$("#ajax").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
		$.ajax( {
			url: "options.py",
			data: {
				haproxyaddserv: $('#haproxyaddserv').val(),
				syn_flood: syn_flood,
				hapver: $('#hapver option:selected' ).val(),
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) { 
			data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1' || data.indexOf('FAILED') != '-1') {
					$("#ajax").html('<div class="alert alert-danger">'+data+'</div>');
				} else if (data.indexOf('success') != '-1' ){
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax").html('<div class="alert alert-success">'+data+'</div>');				
				} else if (data.indexOf('Info') != '-1' ){
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
				} else {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
				}
			}
		} );	
	});	
	$('#nginx_install').click(function() {
		$("#ajax").html('')
		var syn_flood = 0;
		if ($('#nginx_syn_flood').is(':checked')) {
			syn_flood = '1';
		}
		$("#ajax").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
		$.ajax( {
			url: "options.py",
			data: {
				install_nginx: $('#nginxaddserv').val(),
				syn_flood: syn_flood,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) { 
			data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1' || data.indexOf('FAILED') != '-1') {
					$("#ajax").html('<div class="alert alert-danger">'+data+'</div>');
				} else if (data.indexOf('success') != '-1' ){
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax").html('<div class="alert alert-success">'+data+'</div>');				
				} else if (data.indexOf('Info') != '-1' ){
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
				} else {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax").html('<div class="alert alert-info">'+data+'</div>');
				}
			}
		} );	
	});	
	$('#update_haproxy_wi').click(function() {
		$("#ajax-update").html('')
		$("#ajax-update").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
		 $.ajax( {
			url: "options.py",
			data: {
				update_haproxy_wi: 1,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) { 
			data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1' || data.indexOf('Failed') != '-1') {
					$("#ajax").html('<div class="alert alert-danger">'+data+'</div>');
				} else if (data.indexOf('Complete!') != '-1'){
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-success">Update was success!</div>');				
				} else if (data.indexOf('Unauthorized') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-danger">It is seems like you Unauthorized in the HAProxy-WI repository. How to get HAProxy-WI auth you can read <a href="https://haproxy-wi.org/installation.py" title="How to get HAProxy-WI auth">hear</a> </div>');
				} else if (data.indexOf('but not installed') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-warning">You have settings for HAProxy-WI repository, but installed HAProxy-WI without repository. Please reinstall with yum or use update.sh</div>');
				} else if (data.indexOf('No Match for argument') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-warning">It is seems like you do not have HAProxy-WI repository settings. Please read docs for<a href="https://haproxy-wi.org/updates.py">detail</a></div>');
				} else if (data.indexOf('password for') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-warning">It is seems like you need add Apache user to sudoers. Please read docs for<a href="https://haproxy-wi.org/updates.py">detail</a></div>');
				} else if (data.indexOf('No packages marked for update') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-info">It is seems like you have the lastest version HAProxy-WI</div>');
				} else if (data.indexOf('Connection timed out') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-danger">Cannot connect to HAProxy-WI repository. Connection timed out</div>');
				} else if (data.indexOf('--disable') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-danger">It is seems like you have problem with your repositorys.</div>');
				} else if (data.indexOf('Unauthorized') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-danger">It is seems like you Unauthorized in the HAProxy-WI repository.</div>');
				} else if (data.indexOf('Error: Package') != '-1') {
					$('.alert-danger').remove();
					$('.alert-warning').remove();
					$("#ajax-update").html('<div class="alert alert-danger">'+data+'</div>');
				}
			}
		} ); 	
	});	
	$('#add-group').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		$.ajax( {
			url: "options.py",
			data: {
				newgroup: "1",
				groupname: $('#new-group-add').val(),
				newdesc: $('#new-desc').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-group").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					var getId = new RegExp('[0-9]+');
					var id = data.match(getId);
					$("#ajax-group").append(data);
					$( ".newgroup" ).addClass( "update", 1000, callbackGroup );
					$('select:regex(id, group)').append('<option value='+id+'>'+$('#new-group-add').val()+'</option>').selectmenu("refresh");
					$.getScript(awesome);
				}
			}					
		} );
	});	
	$('#add-ssh').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		var ssh_enable = 0;
		if ($('#new-ssh_enable').is(':checked')) {
			ssh_enable = '1';
		}
		$.ajax( {
			url: "options.py",
			data: {
				new_ssh: $('#new-ssh-add').val(),
				new_group: $('#new-sshgroup').val(),
				ssh_user: $('#ssh_user').val(),
				ssh_pass: $('#ssh_pass').val(),
				ssh_enable: ssh_enable,
				page: cur_url[0],
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-ssh").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					var getId = new RegExp('ssh-table-[0-9]+');
					var id = data.match(getId) + '';
					id = id.split('-').pop();;
					$("#ssh_enable_table").append(data);
					$( ".new_ssh" ).addClass( "update", 1000 );
					setTimeout(function() {
						$( ".new_ssh" ).removeClass( "update" );
					}, 2500 );
					$('select:regex(id, credentials)').append('<option value='+id+'>'+$('#new-ssh-add').val()+'</option>').selectmenu("refresh");
					$('select:regex(id, ssh-key-name)').append('<option value='+$('#new-ssh-add').val()+'>'+$('#new-ssh-add').val()+'</option>').selectmenu("refresh");
					$.getScript(awesome);
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( "select" ).selectmenu();
				}
			}					
		} );
	});
	$('#add-telegram').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		$.ajax( {
			url: "options.py",
			data: {
				newtelegram: $('#telegram-token-add').val(),
				chanel: $('#telegram-chanel-add').val(),
				telegramgroup: $('#new-telegram-group-add').val(),
				page: cur_url[0],
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-telegram").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					$("#checker_table").append(data);
					$( ".newgroup" ).addClass( "update", 1000, callbackGroup );
					$.getScript(awesome);
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( "select" ).selectmenu();
				}
			}					
		} );
	});
	function callbackGroup() {
		setTimeout(function() {
			$( ".newgroup" ).removeClass( "update" );
		}, 2500 );
    }
	
	$('#add-user-button').click(function() {
		addUserDialog.dialog('open');
	});
	$('#add-group-button').click(function() {
		if ($('#group-add-table').css('display', 'none')) {
			$('#group-add-table').show("blind", "fast");
		} else {
			$('#group-add-table').hide("blind", "fast");
		}
	});
	var addUserDialog = $( "#user-add-table" ).dialog({
			autoOpen: false,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: "Add new user",
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: {
				"Add": function() {	
					addUser();
				},
				Cancel: function() {
					$( this ).dialog( "close" );
					clearTips();
				}
			}
		});
	var addServerDialog = $( "#server-add-table" ).dialog({
			autoOpen: false,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: "Add new server",
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: {
				"Add": function() {	
					addServer();
				},
				Cancel: function() {
					$( this ).dialog( "close" );
					clearTips();
				}
			}
		});
	$('#add-server-button').click(function() {
		addServerDialog.dialog('open');		
	});
	$('#add-ssh-button').click(function() {
		if ($('#ssh-add-table').css('display', 'none')) {
			$('#ssh-add-table').show("blind", "fast");
		} 
	});
	$('#add-telegram-button').click(function() {
		if ($('#telegram-add-table').css('display', 'none')) {
			$('#telegram-add-table').show("blind", "fast");
		} 
	});
	var addBackupDialog = $( "#backup-add-table" ).dialog({
			autoOpen: false,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: "Create a new backup job",
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: {
				"Add": function() {	
					addBackup();
				},
				Cancel: function() {
					$( this ).dialog( "close" );
					clearTips();
				}
			}
		});
	$('#add-backup-button').click(function() {
		addBackupDialog.dialog('open');		
	});
	$( "#ajax-users input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateUser(id[1])
	});
	$( "#ajax-users select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateUser(id[1])
	});
	$( "#ajax-group input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateGroup(id[1])
	});
	$( "#ajax-servers input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateServer(id[1])
	});
	$( "#ajax-servers select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateServer(id[1])
	});
	$( "#ssh_enable_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSSH(id[1])
		sshKeyEnableShow(id[1])
	});
	$( "#ssh_enable_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSSH(id[1])
		sshKeyEnableShow(id[1])
	});
	$( "#settings input" ).change(function() {
		var id = $(this).attr('id');
		var val = $(this).val();
		updateSettings(id, val);
	});
	$('#new-ssh_enable').click(function() {
		if ($('#new-ssh_enable').is(':checked')) {
			$('#ssh_pass').css('display', 'none');
		} else {
			$('#ssh_pass').css('display', 'block');
		}
	});
	if ($('#new-ssh_enable').is(':checked')) {
		$('#ssh_pass').css('display', 'none');
	} else {
		$('#ssh_pass').css('display', 'block');
	}
   $( "#checker_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateTelegram(id[2])
	});
	$( "#checker_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateTelegram(id[1])
	});
	$( "#ajax-backup-table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$( "#ajax-backup-table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$('#search_ldap_user').click(function() {
		var valid = true;
		$('#error').remove();	
		allFields = $( [] ).add( $('#new-username') ) 
		allFields.removeClass( "ui-state-error" );
		valid = valid && checkLength( $('#new-username'), "user name", 1 );
		user = $('#new-username').val()
		if (valid) {
			$.ajax( {
				url: "options.py",
				data: {
					get_ldap_email: $('#new-username').val(),
					token: $('#token').val()
				},
				type: "POST",
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error') != '-1') {
						alert(data)
						$('#new-email').val('');
						$('#new-password').attr('readonly', false);	
						$('#new-password').val('');	
					} else {
						var json = $.parseJSON(data);
						$('.alert-danger').remove();
						$('#new-email').val(json[0]);
						$('#new-username').val(user+'@'+json[1]);					
						$('#new-password').val('aduser');					
						$('#new-password').attr('readonly', true);					
					}	
				}
			} );
			clearTips();
		}
	});
	
} );

function updateTips( t ) {	
	var tips = $( ".validateTips" );
	tips.text( t ).addClass( "alert-warning" );
}
function clearTips() {
	var tips = $( ".validateTips" );
	tips.html('Form fields tag "<span class="need-field">*</span>" are required.').removeClass( "alert-warning" );
	allFields = $( [] ).add( $('#new-server-add') ).add( $('#new-ip') ).add( $('#new-port')).add( $('#new-username') ).add( $('#new-password') ) 
	allFields.removeClass( "ui-state-error" );
}
function checkLength( o, n, min ) {
	if ( o.val().length < min ) {
		o.addClass( "ui-state-error" );
		updateTips("Filed "+n+" required");
        return false;
	} else {
		return true;
	}
}
function addUser() {
	var valid = true;
	$('#error').remove();	
	allFields = $( [] ).add( $('#new-username') ).add( $('#new-password') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-username'), "user name", 1 );
	valid = valid && checkLength( $('#new-password'), "password", 1 );
	var activeuser = 0;
	if ($('#activeuser').is(':checked')) {
		activeuser = '1';
	}
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newuser: "1",
				newusername: $('#new-username').val(),
				newpassword: $('#new-password').val(),
				newemail: $('#new-email').val(),
				newrole: $('#new-role').val(),
				activeuser: activeuser,
				page: cur_url[0],
				newgroupuser: $('#new-group').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-users").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					$('.alert-danger').remove();
					$("#ajax-users").append(data);											
				}	
			}
		} );
		clearTips();
		$( "#user-add-table" ).dialog("close" );
	}
}
function addServer() {
	$('#error').remove();	
	$('.alert-danger').remove();	
	var valid = true;
	var servername = $('#new-server-add').val();
	var newip = $('#new-ip').val();
	var newservergroup = $('#new-server-group-add').val();
	var cred = $('#credentials').val();
	var typeip = 0;
	var enable = 0;
	var haproxy = 0;
	var nginx = 0;
	if ($('#typeip').is(':checked')) {
		typeip = '1';
	}
	if ($('#enable').is(':checked')) {
		enable = '1';
	}
	if ($('#haproxy').is(':checked')) {
		haproxy = '1';
	}
	if ($('#nginx').is(':checked')) {
		nginx = '1';
	}
	allFields = $( [] ).add( $('#new-server-add') ).add( $('#new-ip') ).add( $('#new-port') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-server-add'), "Hostname", 1 );
	valid = valid && checkLength( $('#new-ip'), "IP", 1 );
	valid = valid && checkLength( $('#new-port'), "Port", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newserver: "1",
				servername: servername,
				newip: newip,
				newport: $('#new-port').val(),
				newservergroup: newservergroup,
				typeip: typeip,
				haproxy: haproxy,
				nginx: nginx,
				enable: enable,
				slave: $('#slavefor' ).val(),
				cred: cred,
				page: cur_url[0],
				desc: $('#desc').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-servers").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					$('.alert-danger').remove();
					$("#ajax-servers").append(data);
					$(".newserver").addClass( "update", 1000 );
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( ".controlgroup" ).controlgroup();
					$( "select" ).selectmenu();
					$.getScript(awesome);
					setTimeout(function() {
						$( ".newserver" ).removeClass( "update" );
					}, 2500 );							
				}
			}					
		} );
		clearTips();
		$( "#server-add-table" ).dialog("close" );
	}
}
function addBackup() {
	var valid = true;
	$('#error').remove();	
	allFields = $( [] ).add( $('#backup-server') ).add( $('#rserver') ).add( $('#rpath') ).add( $('#backup-time') ).add( $('#backup-credentials') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#backup-server'), "backup server ", 1 );
	valid = valid && checkLength( $('#rserver'), "remote server", 1 );
	valid = valid && checkLength( $('#rpath'), "remote path", 1 );
	valid = valid && checkLength( $('#backup-time'), "backup time", 1 );
	valid = valid && checkLength( $('#backup-credentials'), "backup credentials", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				backup: '1',
				server: $('#backup-server').val(),
				rserver: $('#rserver').val(),
				rpath: $('#rpath').val(),
				type: $('#backup-type').val(),
				time: $('#backup-time').val(),
				cred: $('#backup-credentials').val(),
				description: $('#backup-description').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-backup").html('<div class="alert alert-danger" style="width: 50%;">'+data+'</div><br /><br />');
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else if (data.indexOf('success') != '-1') {
					$('.alert-danger').remove();
					$("#ajax-backup-table").append(data);
					$(".newbackup").addClass( "update", 1000 );
					setTimeout(function() {
						$( ".newbackup" ).removeClass( "update" );
					}, 2500 );		
					$( "select" ).selectmenu();
					$.getScript(awesome);														
				} else if (data.indexOf('info') != '-1') {
					$('.alert-danger').remove();
					$("#ajax-backup").html('<div class="alert alert-info">'+data+'</div><br />');											
				}	
			}
		} );
		clearTips();
		$( "#backup-add-table" ).dialog("close" );
	}
}
function updateSettings(param, val) {
	$('.alert-danger').remove();
	$.ajax( {
		url: "options.py",
		data: {
			updatesettings: param,
			val: val,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax").append(data);
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else {
				$('.alert-danger').remove();
				$("#"+param).parent().parent().addClass( "update", 1000 );
			setTimeout(function() {
				$( "#"+param ).parent().parent().removeClass( "update" );
			}, 2500 );
			}
		}
	} );
}
function sshKeyEnableShow(id) {
	$('#ssh_enable-'+id).click(function() {
		if ($('#ssh_enable-'+id).is(':checked')) {
			$('#ssh_pass-'+id).css('display', 'none');
		} else {
			$('#ssh_pass-'+id).css('display', 'block');
		}
	});
	if ($('#ssh_enable-'+id).is(':checked')) {
		$('#ssh_pass-'+id).css('display', 'none');
	} else {
		$('#ssh_pass-'+id).css('display', 'block');
	}
}

function confirmDeleteUser(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#login-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeUser(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function confirmDeleteGroup(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#name-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeGroup(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function confirmDeleteServer(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#hostname-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeServer(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function confirmDeleteSsh(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#ssh_name-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeSsh(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function confirmDeleteTelegram(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#telegram-chanel-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeTelegram(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function confirmDeleteBackup(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete job for" +$('#backup-server-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeBackup(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function cloneServer(id) {
	$( "#add-server-button" ).trigger( "click" );
	if ($('#enable-'+id).is(':checked')) {
		$('#enable').prop('checked', true)
	} else {
		$('#enable').prop('checked', false)
	}
	if ($('#typeip-'+id).is(':checked')) {
		$('#typeip').prop('checked', true)
	} else {
		$('#typeip').prop('checked', false)
	}
	if ($('#haproxy-'+id).is(':checked')) {
		$('#haproxy').prop('checked', true)
	} else {
		$('#haproxy').prop('checked', false)
	}
	if ($('#nginx-'+id).is(':checked')) {
		$('#nginx').prop('checked', true)
	} else {
		$('#nginx').prop('checked', false)
	}
	$('#enable').checkboxradio("refresh");
	$('#typeip').checkboxradio("refresh");
	$('#haproxy').checkboxradio("refresh");
	$('#nginx').checkboxradio("refresh");
	$('#new-server-add').val($('#hostname-'+id).val())
	$('#new-ip').val($('#ip-'+id).val())
	$('#new-port').val($('#port-'+id).val())
	$('#desc').val($('#desc-'+id).val())
	$('#slavefor').val($('#slavefor-'+id+' option:selected').val()).change()
	$('#slavefor').selectmenu("refresh");
	$('#credentials').val($('#credentials-'+id+' option:selected').val()).change()
	$('#credentials').selectmenu("refresh");
	cur_url = cur_url[0].split('#')[0]
	if (cur_url == 'users.py') {
		$('#new-server-group-add').val($('#servergroup-'+id+' option:selected').val()).change()
		$('#new-server-group-add').selectmenu("refresh");
	}
}
function cloneUser(id) {
	$( "#add-user-button" ).trigger( "click" );
	if ($('#activeuser-'+id).is(':checked')) {
		$('#activeuser').prop('checked', true)
	} else {
		$('#activeuser').prop('checked', false)
	}
	$('#activeuser').checkboxradio("refresh");
	$('#new-role').val($('#role-'+id+' option:selected').val()).change()
	$('#new-role').selectmenu("refresh");
	cur_url = cur_url[0].split('#')[0]
	if (cur_url == 'users.py') {
		$('#new-group').val($('#usergroup-'+id+' option:selected').val()).change();
		$('#new-group').selectmenu("refresh");
	}
}
function cloneTelegram(id) {
	$( "#add-telegram-button" ).trigger( "click" );
	$('#telegram-token-add').val($('#telegram-token-'+id).val())
	$('#telegram-chanel-add').val($('#telegram-chanel-'+id).val())
}
function cloneBackup(id) {
	$( "#add-backup-button" ).trigger( "click" );
	$('#rserver').val($('#backup-rserver-'+id).val())
	$('#rpath').val($('#backup-rpath-'+id).val())
	$('#backup-type').val($('#backup-type-'+id+' option:selected').val()).change()
	$('#backup-type').selectmenu("refresh");
	$('#backup-time').val($('#backup-time-'+id+' option:selected').val()).change()
	$('#backup-time').selectmenu("refresh");
	$('#backup-credentials').val($('#backup-credentials-'+id+' option:selected').val()).change()
	$('#backup-credentials').selectmenu("refresh");
}
function removeUser(id) {
	$("#user-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			userdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#user-"+id).remove();
			}
		}					
	} );
}
function removeServer(id) {
	$("#server-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			serverdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#server-"+id).remove();
			}
		}					
	} );	
}
function removeGroup(id) {
	$("#group-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			groupdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#group-"+id).remove();
				$('select:regex(id, group) option[value='+id+']').remove();
				$('select:regex(id, group)').selectmenu("refresh");
			}
		}					
	} );	
}
function removeSsh(id) {
	$("#ssh-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			sshdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#ssh-table-"+id).remove();
				$('select:regex(id, credentials) option[value='+id+']').remove();
				$('select:regex(id, credentials)').selectmenu("refresh");
			}
		}					
	} );	
}
function removeTelegram(id) {
	$("#telegram-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			telegramdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#telegram-table-"+id).remove();
			}
		}					
	} );	
}
function removeBackup(id) {
	$("#backup-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			deljob: id,
			cred: $('#backup-credentials-'+id).val(),
			server: $('#backup-server-'+id).text(),
			rserver: $('#backup-rserver-'+id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data.indexOf('Ok') != '-1') {
				$("#backup-table-"+id).remove();
			}
		}					
	} );	
}
function updateUser(id) {
	$('.alert-danger').remove();
	cur_url[0] = cur_url[0].split('#')[0]
	console.log(cur_url[0])
	if (cur_url[0] != "servers.py") {
		var usergroup = $('#usergroup-'+id+' option:selected' ).val();
	} else {
		var usergroup = $('#usergroup-'+id ).val();
	}
	var activeuser = 0;
	if ($('#activeuser-'+id).is(':checked')) {
		activeuser = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateuser: $('#login-'+id).val(),
			email: $('#email-'+id).val(),
			role: $('#role-'+id).val(),
			usergroup: usergroup,
			activeuser: activeuser,
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-users").append(data);
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else {
				$('.alert-danger').remove();
				$("#user-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#user-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function updateGroup(id) {
	$('#error').remove();	
	$.ajax( {
		url: "options.py",
		data: {
			updategroup: $('#name-'+id).val(),
			descript: $('#descript-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-group").append(data);
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else {
				$('.alert-danger').remove();
				$("#group-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#group-"+id ).removeClass( "update" );
				}, 2500 );
				$('select:regex(id, group) option[value='+id+']').remove();
				$('select:regex(id, group)').append('<option value='+id+'>'+$('#name-'+id).val()+'</option>').selectmenu("refresh");
			}
		}
	} );
}
function updateServer(id) {
	$('.alert-danger').remove();
	var typeip = 0;
	var enable = 0;
	var haproxy = 0;
	var nginx = 0;
	if ($('#typeip-'+id).is(':checked')) {
		typeip = '1';
	}
	if ($('#haproxy-'+id).is(':checked')) {
		haproxy = '1';
	}
	if ($('#nginx-'+id).is(':checked')) {
		nginx = '1';
	}
	if ($('#enable-'+id).is(':checked')) {
		enable = '1';
	}
	var servergroup = $('#servergroup-'+id+' option:selected' ).val();
	console.log(cur_url[0])
	if (cur_url[0].split('#')[0] == "servers.py") {
		 servergroup = $('#new-server-group-add').val();
		 console.log('1')
	}
	console.log(servergroup)
	$.ajax( {
		url: "options.py",
		data: {
			updateserver: $('#hostname-'+id).val(),
			port: $('#port-'+id).val(),
			servergroup: servergroup,
			typeip: typeip,
			haproxy: haproxy,
			nginx: nginx,
			enable: enable,
			slave: $('#slavefor-'+id+' option:selected' ).val(),
			cred: $('#credentials-'+id+' option:selected').val(),
			id: id,
			desc: $('#desc-'+id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-servers").append(data);
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else {
				$('.alert-danger').remove();
				$("#server-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#server-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function uploadSsh() {
	$('.alert-danger').remove();
	if ($( "#ssh-key-name option:selected" ).val() == "Choose server" || $('#ssh_cert').val() == '') {
		$("#ajax-ssh").html('<div class="alert alert-danger" style="margin: 10px;">All fields must be completed</div>');
	} else {
		$.ajax( {
			url: "options.py",
			data: {
				ssh_cert: $('#ssh_cert').val(),
				name: $('#ssh-key-name').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('danger') != '-1') {
						$("#ajax-ssh").html(data);
					} else if (data.indexOf('success') != '-1') {
						$('.alert-danger').remove();
						$("#ajax-ssh").html(data);				
					} else {
						$("#ajax-ssh").html('<div class="alert alert-danger">Something wrong, check and try again</div>');
					}
			}
		} );
	}
}
function updateSSH(id) {
	$('#error').remove();	
	var ssh_enable = 0;
	if ($('#ssh_enable-'+id).is(':checked')) {
		ssh_enable = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updatessh: 1,
			name: $('#ssh_name-'+id).val(),
			group: $('#sshgroup-'+id).val(),
			ssh_enable: ssh_enable,
			ssh_user: $('#ssh_user-'+id).val(),
			ssh_pass: $('#ssh_pass-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-ssh").append(data);
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else {
				$('.alert-danger').remove();
				$("#ssh-table-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#ssh-table-"+id ).removeClass( "update" );
				}, 2500 );
				$('select:regex(id, credentials) option[value='+id+']').remove();
				$('select:regex(id, ssh-key-name) option[value='+$('#ssh_name-'+id).val()+']').remove();
				$('select:regex(id, credentials)').append('<option value='+id+'>'+$('#ssh_name-'+id).val()+'</option>').selectmenu("refresh");
				$('select:regex(id, ssh-key-name)').append('<option value='+$('#ssh_name-'+id).val()+'>'+$('#ssh_name-'+id).val()+'</option>').selectmenu("refresh");
			}
		}
	} );
}
function updateTelegram(id) {
	$('#error').remove();	
	$.ajax( {
		url: "options.py",
		data: {
			updatetoken: $('#telegram-token-'+id).val(),
			updategchanel: $('#telegram-chanel-'+id).val(),
			updategroup: $('#telegramgroup-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-ssh").append(data);
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else {
				$('.alert-danger').remove();
				$("#telegram-table-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#telegram-table-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function updateBackup(id) {
	$('#error').remove();	
	if ($( "#backup-type-"+id+" option:selected" ).val() == "Choose server" || $('#backup-rserver-'+id).val() == '' || $('#backup-rpath-'+id).val() == '') {
		$("#ajax-backup").html('<div class="alert alert-danger" style="margin: 10px;">All fields must be completed</div>');
	} else {
		console.log($('#backup-credentials-'+id).val())
		console.log($('#backup-rpath-'+id).val())
		console.log($('#backup-type-'+id).val())
		console.log($('#backup-server-'+id).text())
		console.log($('#backup-rserver-'+id).val())
		$.ajax( {
			url: "options.py",
			data: {
				backupupdate: id,
				server: $('#backup-server-'+id).text(),
				rserver: $('#backup-rserver-'+id).val(),
				rpath: $('#backup-rpath-'+id).val(),
				type: $('#backup-type-'+id).val(),
				time: $('#backup-time-'+id).val(),
				cred: $('#backup-credentials-'+id).val(),
				description: $('#backup-description-'+id).val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-backup").html('<div class="alert alert-danger" style="margin: 10px;">'+data+'</div>');
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					$('.alert-danger').remove();
					$("#backup-table-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#backup-table-"+id ).removeClass( "update" );
					}, 2500 );
				}
			}
		} );
	}
}
function showApacheLog(serv) {
	var rows = $('#rows').val()
	var grep = $('#grep').val()
	var hour = $('#time_range_out_hour').val()
	var minut = $('#time_range_out_minut').val()
	var hour1 = $('#time_range_out_hour1').val()
	var minut1 = $('#time_range_out_minut1').val()
	$.ajax( {
		url: "options.py",
		data: {
			rows1: rows,
			serv: serv,
			grep: grep,
			hour: hour,
			minut:minut,
			hour1: hour1,
			minut1: minut1,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0]+"?serv="+serv+"&rows1="+rows+"&grep="+grep+
															'&hour='+hour+
															'&minut='+minut+
															'&hour1='+hour1+
															'&minut1='+minut1);
		}					
	} );
}
function checkSshConnect(ip) {
	$.ajax( {
		url: "options.py",
		data: {
			checkSshConnect: 1,
			serv: ip,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('danger') != '-1') {
				$("#ajax").html(data);
			} else {
				$("#ajax").html("<div class='alert alert-success' style='margin: 0;'>Connect accept<a title='Close' id='errorMess'><b>X</b></a></div>");
			}
			$('#errorMess').click(function() {
				$('#error').remove();
				$('.alert-danger').remove();
				$('.alert-success').remove();
			});
		}					
	} );
}
function openChangeUserPasswordDialog(id) {
	changeUserPasswordDialog(id);
}
function changeUserPasswordDialog(id) {
	$( "#user-change-password-table" ).dialog({
			autoOpen: true,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: "Change "+$('#login-'+id).val()+" password",
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: {
				"Change": function() {	
					changeUserPassword(id, $(this));
				},
				Cancel: function() {
					$( this ).dialog( "close" );
					$('#missmatchpass').hide();
				}
			}
		});
}
function changeUserPassword(id, d) {
	var pass = $('#change-password').val();
	var pass2 = $('#change2-password').val();
	if(pass != pass2) {
		$('#missmatchpass').show();
	} else {
		$('#missmatchpass').hide();
		$('#error').remove();	
		$.ajax( {
			url: "options.py",
			data: {
				updatepassowrd: pass,
				id: id,
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-users").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
				} else {
					$('.alert-danger').remove();
					$("#user-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#user-"+id ).removeClass( "update" );
					}, 2500 );
					d.dialog( "close" );
				}
			}
		} );
	}
}