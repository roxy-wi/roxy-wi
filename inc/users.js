var users = '/inc/usersdop.js'
var awesome = "/inc/fontawesome.min.js"

$( function() {
	$('.alert-danger').remove();	

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
					$( "#ajax-users tr td" ).addClass( "update", 1000, callbackUser );					
					$.getScript(url);					
					$.getScript(awesome);	
					$.getScript(users);					
				}	
			}
		} );
	});
	$('#add-group').click(function() {
		$.ajax( {
			url: "sql.py",
			data: {
				newgroup: $('#new-group-add').val(),
				newdesc: $('#new-desc').val(),
			},
			type: "GET",
			success: function( data ) {
				$("#ajax-group").append(data);
				$( "#ajax-group tr td" ).addClass( "update", 1000, callbackGroup );
				window.location.reload(); 
			}					
		} );
	});
	$('#add-server').click(function() {
		$('#error').remove();	
		var typeip;
		if ($('#typeip').is(':checked')) {
			typeip = '1';
		}
		$.ajax( {
			url: "sql.py",
			data: {
				newserver: $('#new-server-add').val(),
				newip: $('#new-ip').val(),
				newservergroup: $('#new-server-group-add').val(),
				typeip: typeip
			},
			type: "GET",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error') != '-1') {
					$("#ajax-servers").append(data);
					$.getScript(users);
				} else {
					$('.alert-danger').hide();
					$("#ajax-servers").append(data);
					$( "#ajax-servers tr td" ).addClass( "update", 1000, callback );					
					$.getScript(url);
					$.getScript(awesome);
					$.getScript(users);
				}
			}					
		} );
	});
	
	function callbackUser() {
		setTimeout(function() {
			$( "#ajax-users tr td" ).removeClass( "update" );
		}, 2500 );
    }
	function callback() {
		setTimeout(function() {
			$( "#ajax-servers tr td" ).removeClass( "update" );
		}, 2500 );
    }
	
	function callbackGroup() {
		setTimeout(function() {
			$( "#ajax-group tr td" ).removeClass( "update" );
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
				}
			}					
		} );	
	}
function updateUser(id) {
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
				if (data == "All fields must be completed ") {
					alert(data);
				} else {
					$("#user-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#user-"+id ).removeClass( "update" );
					}, 2500 );
			}
		}
	} );
}
function updateGroup(id) {
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
				if (data == "All fields must be completed ") {
					alert(data);
				} else {
					$("#group-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#group-"+id ).removeClass( "update" );
					}, 2500 );
			}
		}
	} );
}
function updateServer(id) {
	var typeip;
	if ($('#typeip-'+id).is(':checked')) {
		typeip = '1';
	}
	$.ajax( {
		url: "sql.py",
		data: {
			updateserver: $('#hostname-'+id).val(),
			ip: $('#ip-'+id).val(),
			servergroup: $('#servergroup-'+id+' option:selected' ).val(),
			typeip: typeip,
			id: id
		},
		type: "GET",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
				if (data == "All fields must be completed ") {
					alert(data);
				} else {
					$("#server-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#server-"+id ).removeClass( "update" );
					}, 2500 );
			}
		}
	} );
}