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
					if (data.indexOf('error') != '-1') {
						alert(data)	
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
					if (data.indexOf('error') != '-1') {
						$("#ajaxmaxconn").html('<div class="alert alert-danger" style="margin: 10px;">'+data+'</div>');
					} else {
						$("#ajaxmaxconn").html('<div class="alert alert-success" style="margin: 10px;">'+data+'</div>');
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
				if (data.indexOf('error') != '-1') {
					alert(data)	
				} else {
					var value = data.split('<br>')
					$('#ipbackend').find('option').remove();
					$('#ipbackend').append($("<option></option>").attr("value","disabled").text("Choose Backend"));
						
					for(let i = 0; i < data.split('<br>').length; i++){
						if(value[i] != '') {
						$('#ipbackend').append($("<option></option>")
							.attr("value",value[i])
							.text(value[i]));
						}
					}
					$('#ipbackend').selectmenu("refresh");
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
				if (data.indexOf('error') != '-1') {
					alert(data)	
				} else {
					var value = data.split('<br>')
					$('#backend_server').find('option').remove();
					$('#backend_server').append($("<option></option>").attr("value","disabled").text("Choose Server"));
							
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
				if (data.indexOf('error') != '-1') {
					alert(data)	
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
					if (data.indexOf('error') != '-1') {
						$("#ajaxip").html('<div class="alert alert-danger" style="margin: 10px;">'+data+'</div>');
					} else {
						$("#ajaxip").html('<div class="alert alert-success" style="margin: 10px;">'+data+'</div>');
					}	
			}
		} );
		return false;
	});
});
