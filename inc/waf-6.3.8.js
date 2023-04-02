var awesome = "/inc/fontawesome.min.js"
var waf = "/inc/waf-6.3.8.js"
var overview = "/inc/overview-6.3.9.js"
function showOverviewWaf(serv, hostnamea) {
	var service = findGetParameter('service');
	if (service == 'haproxy') {
		$.getScript('/inc/chart.min.js');
		showWafMetrics();
	}
	var i;
	for (i = 0; i < serv.length; i++) { 
		showOverviewWafCallBack(serv[i], hostnamea[i])
	}
	$.getScript(overview);
	$.getScript(waf);
}
function showOverviewWafCallBack(serv, hostnamea) {
	var service = findGetParameter('service');
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewwaf",
			serv: serv,
			service: service,
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
			$.getScript(overview);
			$.getScript(awesome);
		}				
	} );
}
function metrics_waf(name) {
	var enable = 0;
	if ($('#'+name).is(':checked')) {
		enable = '1';
	}
	name = name.split('metrics')[1]
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
function installWaf(ip1) {
	$("#ajax").html('');
	$("#ajax").html(wait_mess);
	var service = findGetParameter('service');
	$.ajax( {
		url: "options.py",
		data: {
			installwaf: ip1,
			service: service,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) { 
		data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1' || data.indexOf('fatal') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('Info') != '-1' ){
				toastr.clear();
				toastr.info(data);
			} else if (data.indexOf('success') != '-1' ){
				toastr.clear();
				toastr.success('WAF service has been installed');
				showOverviewWaf(ip, hostnamea);
				$("#ajax").html('');
			}	
		}
	} );	
}
function changeWafMode(id) {
	var waf_mode = $('#'+id+' option:selected').val();
	var server_hostname = id.split('_')[0];
	var service = findGetParameter('service');
	 $.ajax( {
		url: "options.py",
		data: {
			change_waf_mode: waf_mode,
			server_hostname: server_hostname,
			service: service,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			toastr.info('Do not forget restart WAF service');
			$( '#'+server_hostname+'-select-line' ).addClass( "update", 1000 );										
			setTimeout(function() {
				$( '#'+server_hostname+'-select-line' ).removeClass( "update" );
			}, 2500 );
		}
	} ); 
}
$( function() {
	$( "#waf_rules input" ).change(function() {
		var id = $(this).attr('id').split('-');
		waf_rules_en(id[1])
	});
});
function waf_rules_en(id) {
	var enable = 0;
	if ($('#rule_id-'+id).is(':checked')) {
		enable = '1';
	}
	var serv = findGetParameter('serv')
	$.ajax( {
		url: "options.py",
		data: {
			waf_rule_id: id,
			waf_en: enable,
			serv: serv,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('sed:') != '-1' || data.indexOf('error: ') != '-1' ) {
				toastr.error(data);
			} else {
				toastr.info('Do not forget restart WAF service');
				$('#rule-' + id).addClass("update", 1000);
				setTimeout(function () {
					$('#rule-' + id).removeClass("update");
				}, 2500);
			}
		}
	} );
}
function addNewConfig() {
	$( "#add-new-config" ).dialog({
		autoOpen: true,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: "Create a new rule",
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Create": function() {
				var valid = true;
				allFields = $( [] ).add( $('#new_rule_name') ).add( $('#new_rule_description') )
				allFields.removeClass( "ui-state-error" );
				valid = valid && checkLength( $('#new_rule_name'), "New rule name", 1 );
				valid = valid && checkLength( $('#new_rule_description'), "New rule description", 1 );
				if(valid) {
					let new_rule_name = $('#new_rule_name').val();
					let new_rule_description = $('#new_rule_description').val();
					let new_rule_file = new_rule_name.replaceAll(' ','_');
					var service = findGetParameter('service');
					var serv = findGetParameter('serv');
					service = escapeHtml(service);
					new_rule_name = escapeHtml(new_rule_name);
					new_rule_description = escapeHtml(new_rule_description);
					new_rule_file = escapeHtml(new_rule_file);
					serv = escapeHtml(serv);
					$.ajax({
						url: "options.py",
						data: {
							new_waf_rule: new_rule_name,
							new_rule_description: new_rule_description,
							new_rule_file: new_rule_file,
							service: service,
							serv: serv,
							token: $('#token').val()
						},
						type: "POST",
						success: function (data) {
							if (data.indexOf('error:') != '-1') {
								toastr.error(data);
							} else {
								var getId = new RegExp('[0-9]+');
								var id = data.match(getId) + '';
								window.location.replace('waf.py?service=' + service + '&waf_rule_id=' + id + '&serv=' + serv);
							}
						}
					});
					$( this ).dialog( "close" );
				}
			},
			Cancel: function() {
				$( this ).dialog( "close" );
			}
		}
	});
}
