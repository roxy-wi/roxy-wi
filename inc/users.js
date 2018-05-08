var users = '/inc/usersdop.js'
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
	var ipformat = /^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
	$('#create').click(function() {
		var hap = 0;
		if ($('#hap').is(':checked')) {
			hap = '1';
		}
		$("#ajax").html('')
		if( $("#master").val() == "" || $("#slave").val() == "" || $("#interface").val() == "" ||
			$("#vrrp-ip").val() == "") {
				$("#ajax").html('<div class="alert alert-danger">Please fill in all fields</div>')
			} else if(! $("#vrrp-ip").val().match(ipformat)) {
				$("#ajax").html('<div class="alert alert-danger">Please enter IP in "VRRP IP" field</div>')
			} else {
				$("#ajax").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
				$.ajax( {
					url: "options.py",
					data: {
						master: $('#master').val(),
						slave: $('#slave').val(),
						interface: $("#interface").val(),
						vrrpip: $('#vrrp-ip').val(),
						hap: hap
					},
					type: "GET",
					success: function( data ) { 
						data = data.replace(/\s+/g,' ');
						if (data.indexOf('error') != '-1' || data.indexOf('alert') != '-1' || data.indexOf('Failed') != '-1') {
							$("#ajax").html('<div class="alert alert-danger">'+data+'</data>');
						} else if (data.indexOf('success') != '-1' ){
							$('.alert-danger').remove();
							$("#ajax").html('<div class="alert alert-success">All is ready!</data>');				
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
						kp: kp
					},
					type: "GET",
					success: function( data ) { 
						data = data.replace(/\s+/g,' ');
						if (data.indexOf('error') != '-1' || data.indexOf('alert') != '-1' || data.indexOf('Failed') != '-1') {
							$("#ajax").html('<div class="alert alert-danger">'+data+'</data>');
						} else if (data.indexOf('success') != '-1' ){
							$('.alert-danger').remove();
							$("#ajax").html('<div class="alert alert-success">All is ready!</data>');				
						}	
					}
				} );
			}
	});
	$('#install').click(function() {
		$("#ajax").html('')
		$.ajax( {
			url: "options.py",
			data: {
				haproxyaddserv: $('#haproxyaddserv').val(),
				},
			type: "GET",
			success: function( data ) { 
			data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1' || data.indexOf('alert') != '-1' || data.indexOf('Failed') != '-1') {
					$("#ajax").html('<div class="alert alert-danger">'+data+'</data>');
				} else if (data.indexOf('success') != '-1' ){
					$('.alert-danger').remove();
					$("#ajax").html('<div class="alert alert-success">'+data+'</data>');				
				}	
			}
		} );	
	});
	//$('.alert-danger').remove();	

	$('#add-user').click(function() {
		$('#error').remove();	
		$.ajax( {
			url: "sql.py",
			data: {
				newusername: $('#new-username').val(),
				newpassword: $('#new-password').val(),
				newemail: $('#new-email').val(),
				newrole: $('#new-role').val(),
				newgroupuser: $('#new-group').val()
			},
			type: "GET",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-users").append(data);
					$.getScript(users);
				} else {
					$('.alert-danger').remove();
					$("#ajax-users").append(data);
					$( ".newuser" ).addClass( "update", 1000, callbackUser );					
					$.getScript(url);					
					$.getScript(awesome);	
					$.getScript(users);					
				}	
			}
		} );
	});
	$('#add-group').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		$.ajax( {
			url: "sql.py",
			data: {
				newgroup: $('#new-group-add').val(),
				newdesc: $('#new-desc').val(),
			},
			type: "GET",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-group").append(data);
					$.getScript(users);
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
	$('#add-server').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		var typeip = 0;
		var enable = 0;
		if ($('#typeip').is(':checked')) {
			typeip = '1';
		}
		if ($('#enable').is(':checked')) {
			enable = '1';
		}
		$.ajax( {
			url: "sql.py",
			data: {
				newserver: $('#new-server-add').val(),
				newip: $('#new-ip').val(),
				newservergroup: $('#new-server-group-add').val(),
				typeip: typeip,
				enable: enable,
				slave: $('#slavefor option:selected' ).val()
			},
			type: "GET",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-servers").append(data);
					$.getScript(users);
				} else {
					$('.alert-danger').remove();
					$("#ajax-servers").append(data);
					$(".newserver").addClass( "update", 1000, callbackServer );		
					$.getScript(url);	
					$.getScript(awesome);					
				}
			}					
		} );
	});
	
	function callbackUser() {
		setTimeout(function() {
			$( ".newuser" ).removeClass( "update" );
		}, 2500 );
    }
	function callbackServer() {
		setTimeout(function() {
			$( ".newserver" ).removeClass( "update" );
		}, 2500 );
    }	
	function callbackGroup() {
		setTimeout(function() {
			$( ".newgroup" ).removeClass( "update" );
		}, 2500 );
    }
	
	$('#add-user-button').click(function() {
		if ($('#user-add-table').css('display', 'none')) {
			$('#user-add-table').show("blind", "fast");
		} 
	});
	$('#add-group-button').click(function() {
		if ($('#group-add-table').css('display', 'none')) {
			$('#group-add-table').show("blind", "fast");
		} 
	});
	$('#add-server-button').click(function() {
		if ($('#server-add-table').css('display', 'none')) {
			$('#server-add-table').show("blind", "fast");
		} 
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
		updateSSH()
	});
	$('#ssh_enable').click(function() {
		if ($('#ssh_enable').is(':checked')) {
			$('#ssh_pass').css('display', 'none');
		} else {
			$('#ssh_pass').css('display', 'block');
		}
	});
	if ($('#ssh_enable').is(':checked')) {
		$('#ssh_pass').css('display', 'none');
	} else {
		$('#ssh_pass').css('display', 'block');
	}
} );
function removeUser(id) {
	$("#user-"+id).css("background-color", "#f2dede");
	$.ajax( {
			url: "sql.py",
			data: {
				userdel: id,
			},
			type: "GET",
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
			url: "sql.py",
			data: {
				serverdel: id,
			},
			type: "GET",
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
			url: "sql.py",
			data: {
				groupdel: id,
			},
			type: "GET",
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
function updateUser(id) {
	$('.alert-danger').remove();
	$.ajax( {
		url: "sql.py",
		data: {
			updateuser: $('#login-'+id).val(),
			password: $('#password-'+id).val(),
			email: $('#email-'+id).val(),
			role: $('#role-'+id).val(),
			usergroup: $('#usergroup-'+id+' option:selected' ).val(),
			id: id
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-users").append(data);
				$.getScript(users);
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
		url: "sql.py",
		data: {
			updategroup: $('#name-'+id).val(),
			descript: $('#descript-'+id).val(),
			id: id
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-group").append(data);
				$.getScript(users);
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
	if ($('#typeip-'+id).is(':checked')) {
		typeip = '1';
	}
	if ($('#enable-'+id).is(':checked')) {
		enable = '1';
	}
	$.ajax( {
		url: "sql.py",
		data: {
			updateserver: $('#hostname-'+id).val(),
			ip: $('#ip-'+id).val(),
			servergroup: $('#servergroup-'+id+' option:selected' ).val(),
			typeip: typeip,
			enable: enable,
			slave: $('#slavefor-'+id+' option:selected' ).val(),
			id: id
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-servers").append(data);
				$.getScript(users);
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
	$.ajax( {
		url: "options.py",
		data: {
			ssh_cert: $('#ssh_cert').val()
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('danger') != '-1') {
					$("#ajax-ssh").html(data);
				} else if (data.indexOf('success') != '-1') {
					$('.alert-danger').remove();
					$("#ajax-ssh").html(data);
					setTimeout(function() {
						$( "#ajax-ssh").html( "" );
					}, 2500 );
					
				} else {
					$("#ajax-ssh").html('<div class="alert alert-danger">Something wrong, check and try again</div>');
				}
		}
	} );
}
function updateSSH() {
	$('#error').remove();	
	var ssh_enable = 0;
	if ($('#ssh_enable').is(':checked')) {
		ssh_enable = '1';
	}
	$.ajax( {
		url: "sql.py",
		data: {
			updatessh: 1,
			ssh_enable: ssh_enable,
			ssh_user: $('#ssh_user').val(),
			ssh_pass: $('#ssh_pass').val(),
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-ssh").append(data);
				$.getScript(users);
			} else {
				$('.alert-danger').remove();
				$("#ssh_enable_table").addClass( "update", 1000 );
				setTimeout(function() {
					$( "#ssh_enable_table" ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function showApacheLog() {
	$.ajax( {
		url: "options.py",
		data: {
			rows1: $('#rows').val(),
			serv: $("#serv").val(),
			grep: $("#grep").val(),
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0]+"?serv="+$("#serv").val()+"&rows1="+$('#rows').val()+"&grep="+$("#grep").val());
		}					
	} );
}