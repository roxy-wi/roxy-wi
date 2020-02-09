var awesome = "/inc/fontawesome.min.js"

$( function() {
	$( "#ajaxwafstatus input" ).change(function() {
		var id = $(this).attr('id');
		metrics_waf(id);
	});
} );
function showOverviewWaf(serv, hostnamea) {
	$.getScript('/inc/chart.min.js');
	showWafMetrics();
	var i;
	for (i = 0; i < serv.length; i++) { 
		showOverviewWafCallBack(serv[i], hostnamea[i])
	}
	$.getScript('/inc/overview.js');
	$.getScript('/inc/waf.js');
}
function showOverviewWafCallBack(serv, hostnamea) {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewwaf",
			serv: serv,
			token: $('#token').val()
		},
		beforeSend: function() {
			$("#"+hostnamea).html('<img class="loading_small" src="/inc/images/loading.gif" />');
		},
		type: "POST",
		success: function( data ) {
			$("#"+hostnamea).empty();
			$("#"+hostnamea).html(data)		
			$( "input[type=submit], button" ).button();
			$( "input[type=checkbox]" ).checkboxradio();
			$.getScript('/inc/overview.js');
			$.getScript(awesome);
		}				
	} );
}
function metrics_waf(name) {
	var enable = 0;
	if ($('#'+name).is(':checked')) {
		enable = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			metrics_waf: name,
			enable: enable,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			showOverviewWaf(ip, hostnamea);
			setTimeout(function() {
				$( "#"+name ).parent().parent().removeClass( "update" );
			}, 2500 );
		}					
	} );
}
function installWaf(ip) {
	$("#ajax").html('')
	$("#ajax").html('<div class="alert alert-warning">Please don\'t close and don\'t represh page. Wait until the work is completed. This may take some time </div>');
	$.ajax( {
		url: "options.py",
		data: {
			installwaf: ip,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) { 
		data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1' || data.indexOf('Failed') != '-1') {
				$("#ajax").html('<div class="alert alert-danger" style="margin: 15px;">'+data+'</data>');
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else if (data.indexOf('Info') != '-1' ){
				$('.alert-danger').remove();
				$('.alert-warning').remove();
				$("#ajax").html('<div class="alert alert-info">'+data+'</data>');
			} else if (data.indexOf('success') != '-1' ){
				$('.alert-danger').remove();
				$('.alert-warning').remove();
				$("#ajax").html('<div class="alert alert-success">'+data+'</data>');
				showOverviewWaf(ip, hostnamea)
			}	
		}
	} );	
}
function changeWafMode(id) {
	var waf_mode = $('#'+id+' option:selected').val();
	var server_hostname = id.split('_')[0];
	 $.ajax( {
		url: "options.py",
		data: {
			change_waf_mode: waf_mode,
			server_hostname: server_hostname,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			alert('Do not forget restart WAF server: '+server_hostname)
			$( '#'+server_hostname+'-select-line' ).addClass( "update", 1000 );										
			setTimeout(function() {
				$( '#'+server_hostname+'-select-line' ).removeClass( "update" );
			}, 2500 );
		}
	} ); 
}