$( function() {
	$( "#ajaxwafstatus input" ).change(function() {
		var id = $(this).attr('id');
		console.log(id);
		metrics_waf(id);
	});
} );
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
		type: "GET",
		success: function( data ) {
			showOverviewWaf();
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
		type: "GET",
		success: function( data ) { 
		data = data.replace(/\s+/g,' ');
			if (data.indexOf('error') != '-1' || data.indexOf('Failed') != '-1') {
				$("#ajax").html('<div class="alert alert-danger" style="margin: 15px;">'+data+'</data>');
				$('#errorMess').click(function() {
					$('#error').remove();
					$('.alert-danger').remove();
				});
			} else if (data.indexOf('success') != '-1' ){
				$('.alert-danger').remove();
				$('.alert-warning').remove();
				$("#ajax").html('<div class="alert alert-success">'+data+'</data>');
				showOverviewWaf()
			}	
		}
	} );	
}