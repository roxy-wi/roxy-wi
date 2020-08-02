function showRuntime() {
	if($('#save').prop('checked')) {
		saveCheck = "on";
	} else {
		saveCheck = "";
	}
	$.ajax( {
		url: "options.py",
		data: {
			servaction: $('#servaction').val(),
			serv: $("#serv").val(),
			servbackend: $("#servbackend").val(),
			save: saveCheck,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			$("#ajaxruntime").html(data);
		}					
	} );
}
$( function() {
	$('#runtimeapiform').submit(function() {
		showRuntime();
		return false;
	}); 
	$( "#maxconn_select" ).on('selectmenuchange',function()  {
		$.ajax( {
			url: "options.py",
			data: {
				maxconn_select: $('#maxconn_select').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error: ') != '-1') {
						toastr.error(data);
					} else {
						var value = data.split('<br>')
						$('#maxconnfront').find('option').remove();
						$('#maxconnfront').append($("<option></option>").attr("value","disabled").text("Choose Frontend"));
						$('#maxconnfront').append($("<option></option>").attr("value","global").text("global"));
							
						for(let i = 0; i < data.split('<br>').length; i++){
							if(value[i] != '') {
							$('#maxconnfront').append($("<option></option>")
								.attr("value",value[i])
								.text(value[i]));
							}
						}
						$('#maxconnfront').selectmenu("refresh");
					}	
			}
		} );
	});
	$('#maxconnform').submit(function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#maxconn_select').val(),
				maxconn_frontend: $('#maxconnfront').val(),
				maxconn_int: $('#maxconnint').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error: ') != '-1') {
						toastr.error(data);
					} else {
						toastr.success(data);
					}	
			}
		} );
		return false;
	});
	$( "#ip_select" ).on('selectmenuchange',function()  {
		$.ajax( {
			url: "options.py",
			data: {
				ip_select: $('#ip_select').val(),
				serv: $('#ip_select').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					var value = data.split('<br>')
					$('#ipbackend').find('option').remove();
					$('#ipbackend').append($("<option></option>").attr("value","disabled").text("Choose Backend"));
					$('#backend_server').find('option').remove();
					$('#backend_port').val('');
					$('#backend_ip').val('');
					for(let i = 0; i < data.split('<br>').length; i++){
						if(value[i] != '') {
						$('#ipbackend').append($("<option></option>")
							.attr("value",value[i])
							.text(value[i]));
						}
					}
					$('#ipbackend').selectmenu("refresh");
					$('#backend_server').selectmenu("refresh");
				}	
			}
		} );
	});
	$( "#ipbackend" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#ip_select').val(),
				ipbackend: $('#ipbackend').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					var value = data.split('<br>')
					$('#backend_server').find('option').remove();
					$('#backend_server').append($("<option></option>").attr("value","disabled").text("Choose Server"));
					$('#backend_port').val('');
					$('#backend_ip').val('');			
					for(let i = 0; i < data.split('<br>').length; i++){
						if(value[i] != ' ') {						
							value[i] = value[i].replace(/\s+/g,'');
							$('#backend_server').append($("<option></option>")
								.attr("value",value[i])
								.text(value[i]));
						}
					}
					$('#backend_server').selectmenu("refresh");
				}	
			}
		} );
	});
	$( "#backend_server" ).on('selectmenuchange',function() {
		$('#backend_ip').val();
		$('#backend_port').val();
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#ip_select').val(),
				ipbackend: $('#ipbackend').val(),
				backend_server: $('#backend_server').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					var server = data.split(':')[0]
					var port = data.split(':')[1]
					port = port.replace(/\s+/g,'');
					server = server.replace(/\s+/g,'');
					$('#backend_port').val(port);
					$('#backend_ip').val(server);			
				}	
			}
		} );	
	});
	$('#runtimeapiip').submit(function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#ip_select').val(),
				backend_backend: $('#ipbackend').val(),
				backend_server: $('#backend_server').val(),
				backend_ip: $('#backend_ip').val(),
				backend_port: $('#backend_port').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error: ') != '-1') {
						toastr.error(data);
					} else {
						toastr.success(data);
					}	
			}
		} );
		return false;
	});
	$( "#table_serv_select" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#table_serv_select').val(),
				table_serv_select: $('#table_serv_select').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,'');
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					var value = data.split(',')
					$('#table_select').find('option').remove();
					$('#table_select').append($("<option titile='Show all tables'></option>").attr("value","All").text("All"));
							
					for(let i = 0; i < data.split(',').length; i++){
						if(value[i] != '') {						
							value[i] = value[i].replace(/\s+/g,'');
							$('#table_select').append($("<option title=\"Show table "+value[i]+"\"></option>")
								.attr("value",value[i])
								.text(value[i]));
						}
					}
					$('#table_select').selectmenu("refresh");
				}	
			}
		} );
	});
	$('#runtimeapitable').submit(function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#table_serv_select').val(),
				table_select: $('#table_select').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
					if (data.indexOf('error:') != '-1') {
						toastr.error(data);
					} else {
						$("#ajaxtable").html(data);
						$( "input[type=submit], button" ).button();
						$.getScript("/inc/fontawesome.min.js");
						FontAwesomeConfig = { searchPseudoElements: true, observeMutations: false };
					}				
			}
		} );
		return false;
	});
	$('#runtimeapilist').submit(function() {
		getList();
		return false;
	});
	$( "#list_serv_select" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#list_serv_select').val(),
				list_serv_select: $('#list_serv_select').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/, /g, ',');
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					var value = data.split(',');
					$('#list_select').find('option').remove();
					//$('#list_select').append($("<option titile='Show all tables'></option>").attr("value","All").text("All"));

					for (let i = 0; i < data.split(',').length; i++) {
						if (value[i] != '') {
							value[i] = value[i].replace(/\'/g, '');
							value[i] = value[i].replace('(', '');
							value[i] = value[i].replace(')', '');
							value[i] = value[i].replace('[', '');
							value[i] = value[i].replace(']', '');
							id = value[i].split(' ')[0];
							full_text_option = value[i].split(' ')[1]
							text_option = full_text_option.split('/').slice(-2)[0];
							text_option = text_option + '/' + full_text_option.split('/').slice(-1)[0];
							$('#list_select').append($("<option title=\"Show list " + text_option + "\"></option>")
								.attr("value", id)
								.text(text_option));
						}
					}
					$('#list_select').selectmenu("refresh");
				}
			}
		} );
	});


});
function deleteTableEntry(id, table, ip) {
	$(id).parent().parent().css("background-color", "#f2dede");
	$.ajax( {
    	url: "options.py",
    	data: {
    	    serv: $('#table_serv_select').val(),
    		table_for_delete: table,
    		ip_for_delete: ip,
    		token: $('#token').val()
    	},
    	type: "POST",
    	success: function( data ) {
    	    if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
    		} else {
    		    $(id).parent().parent().remove()
    		}
    	}
    } );
}
function getList() {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $('#list_serv_select').val(),
			list_select_id: $('#list_select').val(),
			list_select_name: $('#list_select  option:selected').text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$("#ajaxlist").html(data);
				$( "input[type=submit], button" ).button();
				$.getScript("/inc/fontawesome.min.js");
				FontAwesomeConfig = { searchPseudoElements: true, observeMutations: false };
			}
		}
	} );
}
function deleteListIp(id, list_id, ip_id, ip) {
	toastr.clear();
	$(id).parent().parent().css("background-color", "#f2dede !important");
	$.ajax( {
		url: "options.py",
		data: {
			serv: $('#list_serv_select').val(),
			list_id_for_delete: list_id,
			list_ip_id_for_delete: ip_id,
			list_ip_for_delete: ip,
			list_name: $('#list_add_ip').data("list-name"),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$(id).parent().parent().remove();
				toastr.info('Do not forget upload updated list to the properly server. Restart does not need');
				getList();
			}
		}
	} );
}
function addNewIp() {
	toastr.clear();
	var valid = true;
	allFields = $( [] ).add( $('#list_add_ip_new_ip') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#list_add_ip_new_ip'), "IP", 1 );
	var ip = $('#list_add_ip_new_ip').val();
	console.log($('#list_add_ip_new_ip').val());
	console.log($('#list_add_ip').data("list-id"))
	if(valid) {
		$.ajax({
			url: "options.py",
			data: {
				serv: $('#list_serv_select').val(),
				list_ip_for_add: ip,
				list_id_for_add: $('#list_add_ip').data("list-id"),
				list_name: $('#list_add_ip').data("list-name"),
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					getList();
					$( "#list_add_ip_form" ).dialog("destroy" );
					toastr.success('IP ' + ip + ' has been added');
					toastr.info('Do not forget upload updated list to the properly server. Restart does not need');

				}
			}
		});
	}
}