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
		var syn_flood = 0;
		if ($('#hap').is(':checked')) {
			hap = '1';
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
						syn_flood: syn_flood,
						token: $('#token').val()
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
						kp: kp,
						token: $('#token').val()
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
				token: $('#token').val()
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
		var alert_en = 0;
		var metrics = 0;
		if ($('#typeip').is(':checked')) {
			typeip = '1';
		}
		if ($('#enable').is(':checked')) {
			enable = '1';
		}
		if ($('#alert').is(':checked')) {
			var alert_en = '1';
		}
		if ($('#metrics').is(':checked')) {
			var metrics = '1';
		}
		$.ajax( {
			url: "sql.py",
			data: {
				newserver: $('#new-server-add').val(),
				newip: $('#new-ip').val(),
				newservergroup: $('#new-server-group-add').val(),
				typeip: typeip,
				enable: enable,
				slave: $('#slavefor' ).val(),
				cred: $('#credentials').val(),
				alert_en: alert_en,
				metrics: metrics,
				page: cur_url[0]
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
	
	$('#add-ssh').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		var ssh_enable = 0;
		if ($('#new-ssh_enable').is(':checked')) {
			ssh_enable = '1';
		}
		$.ajax( {
			url: "sql.py",
			data: {
				new_ssh: $('#new-ssh-add').val(),
				new_group: $('#new-sshgroup').val(),
				ssh_user: $('#ssh_user').val(),
				ssh_pass: $('#ssh_pass').val(),
				ssh_enable: ssh_enable,
				page: cur_url[0]
			},
			type: "GET",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-ssh").append(data);
					$.getScript(users);
				} else {
					var getId = new RegExp('ssh-table-[0-9]+');
					var id = data.match(getId) + '';
					id = id.split('-').pop();;
					$("#ssh_enable_table").append(data);
					$( ".newgroup" ).addClass( "update", 1000, callbackGroup );
					$('select:regex(id, credentials)').append('<option value='+id+'>'+$('#new-ssh-add').val()+'</option>').selectmenu("refresh");
					$('select:regex(id, ssh-key-name)').append('<option value='+$('#new-ssh-add').val()+'>'+$('#new-ssh-add').val()+'</option>').selectmenu("refresh");
					$.getScript(awesome);
					$.getScript(url);	
				}
			}					
		} );
	});
	$('#add-telegram').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		$.ajax( {
			url: "sql.py",
			data: {
				newtelegram: $('#telegram-token-add').val(),
				chanel: $('#telegram-chanel-add').val(),
				telegramgroup: $('#new-telegram-group-add').val(),
				page: cur_url[0]
			},
			type: "GET",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-telegram").append(data);
					$.getScript(users);
				} else {
					$("#checker_table").append(data);
					$( ".newgroup" ).addClass( "update", 1000, callbackGroup );
					$.getScript(awesome);
					$.getScript(url);
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
		console.log(id)
		console.log(val)
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
} );
function updateSettings(param, val) {
	$('.alert-danger').remove();
	$.ajax( {
		url: "sql.py",
		data: {
			updatesettings: param,
			val: val
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax").append(data);
				$.getScript(users);
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
function removeSsh(id) {
	$("#ssh-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "sql.py",
		data: {
			sshdel: id,
		},
		type: "GET",
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
		url: "sql.py",
		data: {
			telegramdel: id,
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#telegram-table-"+id).remove();
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
	var alert_en = 0;
	var metrics = 0;
	if ($('#typeip-'+id).is(':checked')) {
		typeip = '1';
	}
	if ($('#enable-'+id).is(':checked')) {
		enable = '1';
	}
	if ($('#alert-'+id).is(':checked')) {
		alert_en = '1';
	}
	if ($('#metrics-'+id).is(':checked')) {
		metrics = '1';
	}
	var servergroup = $('#servergroup-'+id+' option:selected' ).val();
	if (cur_url[0] == "servers.py") {
		 servergroup = $('#servergroup-'+id).val();
	}
	$.ajax( {
		url: "sql.py",
		data: {
			updateserver: $('#hostname-'+id).val(),
			ip: $('#ip-'+id).val(),
			servergroup: servergroup,
			typeip: typeip,
			enable: enable,
			slave: $('#slavefor-'+id+' option:selected' ).val(),
			cred: $('#credentials-'+id+' option:selected').val(),
			id: id,
			metrics: metrics,
			alert_en: alert_en
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
			ssh_cert: $('#ssh_cert').val(),
			name: $('#ssh-key-name').val(),
			token: $('#token').val()
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
function updateSSH(id) {
	$('#error').remove();	
	var ssh_enable = 0;
	if ($('#ssh_enable-'+id).is(':checked')) {
		ssh_enable = '1';
	}
	$.ajax( {
		url: "sql.py",
		data: {
			updatessh: 1,
			name: $('#ssh_name-'+id).val(),
			group: $('#sshgroup-'+id).val(),
			ssh_enable: ssh_enable,
			ssh_user: $('#ssh_user-'+id).val(),
			ssh_pass: $('#ssh_pass-'+id).val(),
			id: id
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-ssh").append(data);
				$.getScript(users);
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
		url: "sql.py",
		data: {
			updatetoken: $('#telegram-token-'+id).val(),
			updategchanel: $('#telegram-chanel-'+id).val(),
			updategroup: $('#telegramgroup-'+id).val(),
			id: id
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1') {
				$("#ajax-ssh").append(data);
				$.getScript(users);
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
function showApacheLog(serv) {
	$.ajax( {
		url: "options.py",
		data: {
			rows1: $('#rows').val(),
			serv: serv,
			grep: $("#grep").val(),
			hour: $('#time_range_out_hour').val(),
			minut: $('#time_range_out_minut').val(),
			hour1: $('#time_range_out_hour1').val(),
			minut1: $('#time_range_out_minut1').val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0]+"?serv="+$("#serv").val()+"&rows1="+$('#rows').val()+"&grep="+$("#grep").val());
		}					
	} );
}