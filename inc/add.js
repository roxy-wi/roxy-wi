var ssl_offloading_var = "http-request set-header X-Forwarded-Port %[dst_port] \n"+
						"http-request add-header X-Forwarded-Proto https if { ssl_fc } \n"+
						"redirect scheme https if !{ ssl_fc } \n"

$( function() {
	$( "#listen-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#listen-mode-select option:selected" ).val() == "tcp") {
			$( "#https-listen-span" ).hide("fast");
			$( "#https-hide-listen" ).hide("fast");
			$("#compression").checkboxradio( "disable" );
			$("#cache").checkboxradio( "disable" );
			$("#ssl_offloading").checkboxradio( "disable" );
			$("#cookie").checkboxradio( "disable" );
			$("#slow_atack").checkboxradio( "disable" );
			$( "#https-listen" ).prop("checked", false);
		} else {
			$( "#https-listen-span" ).show("fast");
			$("#compression").checkboxradio( "enable" );
			$("#cache").checkboxradio( "enable" );
			$("#ssl_offloading").checkboxradio( "enable" );
			$("#cookie").checkboxradio( "enable" );
			$("#slow_atack").checkboxradio( "enable" );
		}
	});
	$( "#frontend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#frontend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-frontend-span" ).hide("fast");
			$( "#https-hide-frontend" ).hide("fast");
			$("#compression2").checkboxradio( "disable" );
			$("#cache2").checkboxradio( "disable" );
			$("#ssl_offloading2").checkboxradio( "disable" );
			$("#cookie2").checkboxradio( "disable" );
			$("#slow_atack1").checkboxradio( "disable" );
		} else {
			$( "#https-frontend-span" ).show("fast");
			$("#compression2").checkboxradio( "enable" );
			$("#cache2").checkboxradio( "enable" );
			$("#ssl_offloading2").checkboxradio( "enable" );
			$("#cookie2").checkboxradio( "enable" );
			$("#slow_atack1").checkboxradio( "enable" );
		}
	});
	$( "#backend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#backend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-backend-span" ).hide("fast");
			$( "#https-hide-backend" ).hide("fast");
			$("#compression3").checkboxradio( "disable" );
			$("#cache3").checkboxradio( "disable" );
			$("#ssl_offloading3").checkboxradio( "disable" );
			$("#cookie3").checkboxradio( "disable" );
			$("#slow_atack2").checkboxradio( "disable" );
		} else {
			$( "#https-backend-span" ).show("fast");
			$("#compression3").checkboxradio( "enable" );
			$("#cache3").checkboxradio( "enable" );
			$("#ssl_offloading3").checkboxradio( "enable" );
			$("#cookie3").checkboxradio( "enable" );
			$("#slow_atack2").checkboxradio( "enable" );
		}
	});
	$( "#https-listen" ).click( function(){
		if ($('#https-listen').is(':checked')) {
			$( "#https-hide-listen" ).show( "fast" );
			$( "#path-cert-listen" ).attr('required',true);
		} else {
			$( "#https-hide-listen" ).hide( "fast" );
			$( "#path-cert-listen" ).prop('required',false);
		}
	});	
	$( "#https-frontend" ).click( function(){
		if ($('#https-frontend').is(':checked')) {
			$( "#https-hide-frontend" ).show( "fast" );
			$( "#path-cert-frontend" ).attr('required',true);
		} else {
			$( "#https-hide-frontend" ).hide( "fast" );
			$( "#path-cert-frontend" ).prop('required',false);
		}
	});	
	$( "#https-backend" ).click( function(){
		if ($('#https-backend').is(':checked')) {
			$( "#https-hide-backend" ).show( "fast" );
		} else {
			$( "#https-hide-backend" ).hide( "fast" );
		}
	});
	$( "#ssl-dis-check-listen" ).click( function(){
		if ($('#ssl-dis-check-listen').is(':checked')) {
			$( "#ssl-check-listen" ).checkboxradio( "disable" );
			$( "#ssl-check-listen" ).prop( "checked", false );
			$( "#ssl-check-listen" ).checkboxradio("refresh");
		} else {
			$( "#ssl-check-listen" ).checkboxradio( "enable" );
			$( "#ssl-check-listen" ).prop( "checked", true );
			$( "#ssl-check-listen" ).checkboxradio("refresh");
		}
	});
	$( "#ssl-dis-check-backend" ).click( function(){
		if ($('#ssl-dis-check-backend').is(':checked')) {
			$( "#ssl-check-backend" ).checkboxradio( "disable" );
			$( "#ssl-check-backend" ).prop( "checked", false );
			$( "#ssl-check-backend" ).checkboxradio("refresh");
		} else {
			$( "#ssl-check-backend" ).checkboxradio( "enable" );
			$( "#ssl-check-backend" ).prop( "checked", true );
			$( "#ssl-check-backend" ).checkboxradio("refresh");
		}
	});
	$( "#options-listen-show" ).click( function(){
		if ($('#options-listen-show').is(':checked')) {
			$( "#options-listen-show-div" ).show( "fast" );
		} else {
			$( "#options-listen-show-div" ).hide( "fast" );
		}
	});	
	$( "#options-frontend-show" ).click( function(){
		if ($('#options-frontend-show').is(':checked')) {
			$( "#options-frontend-show-div" ).show( "fast" );
		} else {
			$( "#options-frontend-show-div" ).hide( "fast" );
		}
	});	
	$( "#options-backend-show" ).click( function(){
		if ($('#options-backend-show').is(':checked')) {
			$( "#options-backend-show-div" ).show( "fast" );
		} else {
			$( "#options-backend-show-div" ).hide( "fast" );
		}
	});	
	$( "#controlgroup-listen-show" ).click( function(){
		if ($('#controlgroup-listen-show').is(':checked')) {
			$( "#controlgroup-listen" ).show( "fast" );
			if ($('#check-servers-listen').is(':checked')) {
				$( "#rise-listen" ).attr('required',true);
				$( "#fall-listen" ).attr('required',true);
				$( "#inter-listen" ).attr('required',true);
				$( "#inter-listen" ).attr('disable',false);				
			}				
		} else {
			$( "#controlgroup-listen" ).hide( "fast" );			
		}
		$( "#check-servers-listen" ).click( function(){
			if ($('#check-servers-listen').is(':checked')) {
				$( "#rise-listen" ).attr('required',true);
				$( "#fall-listen" ).attr('required',true);
				$( "#inter-listen" ).attr('required',true);
				$( "#inter-listen" ).selectmenu( "option", "disabled", false );
				$( "#fall-listen" ).selectmenu( "option", "disabled", false );
				$( "#rise-listen" ).selectmenu( "option", "disabled", false );
			} else {
				$( "#rise-listen" ).attr('required',false);
				$( "#fall-listen" ).attr('required',false);
				$( "#inter-listen" ).attr('required',false);
				$( "#inter-listen" ).selectmenu( "option", "disabled", true );
				$( "#fall-listen" ).selectmenu( "option", "disabled", true );
				$( "#rise-listen" ).selectmenu( "option", "disabled", true );
			}
		});
	});
	$( "#controlgroup-backend-show" ).click( function(){
		if ($('#controlgroup-backend-show').is(':checked')) {
			$( "#controlgroup-backend" ).show( "fast" );
			if ($('#check-servers-backend').is(':checked')) {
				$( "#rise-backend" ).attr('required',true);
				$( "#fall-backend" ).attr('required',true);
				$( "#inter-backend" ).attr('required',true);
			}
		} else {
			$( "#controlgroup-backend" ).hide( "fast" );			
		}
	});
	$( "#circuit_breaking_listen" ).click( function(){
		if ($('#circuit_breaking_listen').is(':checked')) {
			$( "#circuit_breaking_listen_div" ).show( "fast" );
		} else {
			$( "#circuit_breaking_listen_div" ).hide( "fast" );
		}
	});
	$( "#circuit_breaking_backend" ).click( function(){
		if ($('#circuit_breaking_backend').is(':checked')) {
			$( "#circuit_breaking_backend_div" ).show( "fast" );
		} else {
			$( "#circuit_breaking_backend_div" ).hide( "fast" );
		}
	});
	$( "#cookie" ).click( function(){
		if ($('#cookie').is(':checked')) {
			$("#cookie_name" ).attr('required',true);
			$("#cookie_div").show( "fast" );
		} else {
			$("#cookie_name" ).attr('required',false);
			$("#cookie_div").hide( "fast" );
			$("#dynamic-cookie-key" ).attr('required',false);
		}
	});
	$( "#cookie2" ).click( function(){
		if ($('#cookie2').is(':checked')) {
			$("#cookie_name2" ).attr('required',true);
			$("#cookie_div2").show( "fast" );
		} else {
			$("#cookie_name2" ).attr('required',false);
			$("#cookie_div2").hide( "fast" );
			$("#dynamic-cookie-key2" ).attr('required',false);
		}
	});
	$( "#rewrite" ).on('selectmenuchange',function()  {
		if ($( "#rewrite option:selected" ).val() == "insert" || $( "#rewrite option:selected" ).val() == "rewrite") {
			$( "#prefix" ).checkboxradio( "disable" );
		} else {
			$( "#prefix" ).checkboxradio( "enable" );
		}
	});
	$( "#rewrite2" ).on('selectmenuchange',function()  {
		if ($( "#rewrite2 option:selected" ).val() == "insert" || $( "#rewrite2 option:selected" ).val() == "rewrite") {
			$( "#prefix2" ).checkboxradio( "disable" );
		} else {
			$( "#prefix2" ).checkboxradio( "enable" );
		}
	});
	$( "#dynamic" ).click( function(){
		if ($('#dynamic').is(':checked')) {
			$("#dynamic-cookie-key" ).attr('required',true);
			$("#dynamic_div").show("slide", "fast" );
		} else {
			$("#dynamic-cookie-key" ).attr('required',false);
			$("#dynamic_div").hide("slide", "fast" );
		}
	});
	$( "#dynamic2" ).click( function(){
		if ($('#dynamic2').is(':checked')) {
			$("#dynamic-cookie-key2" ).attr('required',true);
			$("#dynamic_div2").show("slide", "fast" );
		} else {
			$("#dynamic-cookie-key2" ).attr('required',false);
			$("#dynamic_div2").hide("slide", "fast" );
		}
	});
	$( "#check-servers-backend" ).click( function(){
		if ($('#check-servers-backend').is(':checked')) {
			$( "#rise-backend" ).attr('required',true);
			$( "#fall-backend" ).attr('required',true);
			$( "#inter-backend" ).attr('required',true);
			$( "#inter-backend" ).selectmenu( "option", "disabled", false );
			$( "#fall-backend" ).selectmenu( "option", "disabled", false );
			$( "#rise-backend" ).selectmenu( "option", "disabled", false );
		} else {
			$( "#rise-backend" ).attr('required',false);
			$( "#fall-backend" ).attr('required',false);
			$( "#inter-backend" ).attr('required',false);
			$( "#inter-backend" ).selectmenu( "option", "disabled", true );
			$( "#fall-backend" ).selectmenu( "option", "disabled", true );
			$( "#rise-backend" ).selectmenu( "option", "disabled", true );
		}
	});
	
	
	var availableTags = [
		"acl", "hdr(host)", "hdr_beg(host)", "hdr_dom(host)", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "set cookie", "dynamic-cookie-key", "mysql-check", "tcpka", "tcplog", "forwardfor", "option"
	];
			
	$( "#ip" ).autocomplete({
		source: function( request, response ) {
			if(!checkIsServerFiled('#serv')) return false;
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					show_ip: request.term,
					serv: $("#serv").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));				
				}					
			} );
		},
		autoFocus: true,
		minLength: -1,
		select: function( event, ui ) {
			$('#listen-port').focus();				
		}
	});
	$( "#ip1" ).autocomplete({
		source: function( request, response ) {
			if(!checkIsServerFiled('#serv2')) return false;
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					show_ip: request.term,
					serv: $("#serv2").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}
			} );
		},
		autoFocus: true,
		minLength: -1,
		select: function( event, ui ) {
			$('#frontend-port').focus();
		}
	});
	$( "#backends" ).autocomplete({
		source: function( request, response ) {
			if(!checkIsServerFiled('#serv2')) return false;
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					backend: request.term,
					serv: $("#serv2").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					response(data.split('<br>'));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#blacklist-hide-input" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					get_lists: request.term,
					color: "black",
					group: $("#group").val(),
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
	$( "#blacklist-hide-input1" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					get_lists: request.term,
					color: "black",
					group: $("#group").val(),
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
	$( "#whitelist-hide-input" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					get_lists: request.term,
					color: "white",
					group: $("#group").val(),
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
	$( "#whitelist-hide-input1" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					get_lists: request.term,
					color: "white",
					group: $("#group").val(),
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
	$( "#new-option" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#new-option").append(ui.item.value + " ")
		}
	});
	$( "#option_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateOptions(id[2])
	});
	$( "#options" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput").append(ui.item.value + " ");
			$(this).val('');
			return false;
		}
	});
	$( "#saved-options" ).autocomplete({
		dataType: "json",
		source: "options.py?getoption="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$("#optionsInput").append(ui.item.value + " \n");
			$(this).val('');
			return false;
		}
	});
	$( "#options1" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput1").append(ui.item.value + " ");
			$(this).val('');
			return false; 
		}
	});
	
	$( "#saved-options1" ).autocomplete({
		dataType: "json",
		source: "options.py?getoption="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$("#optionsInput1").append(ui.item.value + " \n");	
			$(this).val('');
			return false;		
		}
	});
	$( "#options2" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput2").append(ui.item.value + " ");
			$(this).val('');
			return false;
		}
	});
	$( "#saved-options2" ).autocomplete({
		dataType: "json",
		source: "options.py?getoption="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$("#optionsInput2").append(ui.item.value + " \n");	
			$(this).val('');
			return false;
		}
	});
	$('#add-option-button').click(function() {
		if ($('#option-add-table').css('display', 'none')) {
			$('#option-add-table').show("blind", "fast");
		} 
	});
	$('#add-option-new').click(function() {
		$.ajax( {
			url: "options.py",
			data: {
				newtoption: $('#new-option').val(),
				newoptiongroup: $('#group').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					$("#option_table").append(data);
					setTimeout(function() {
						$( ".newoption" ).removeClass( "update" );
					}, 2500 );	
					$.getScript("/inc/fontawesome.min.js");
				}
			}					
		} );
	});
	$( "#servers_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSavedServer(id[2])

	});
	$( '[name=servers]' ).autocomplete({
		source: "options.py?getsavedserver="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$(this).append(ui.item.value + " ");
			$(this).next().focus();
		}
	})
	.autocomplete( "instance" )._renderItem = function( ul, item ) {
		return $( "<li>" )
		.append( "<div>" + item.value + "<br>" + item.desc + "</div>" )
		.appendTo( ul );
    };
	$('#add-saved-server-button').click(function() {
		if ($('#saved-server-add-table').css('display', 'none')) {
			$('#saved-server-add-table').show("blind", "fast");
		} 
	});
	$('#add-saved-server-new').click(function() {
		$.ajax( {
			
			url: "options.py",
			data: {
				newsavedserver: $('#new-saved-servers').val(),
				newsavedservergroup: $('#group').val(),
				newsavedserverdesc: $('#new-saved-servers-description').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					$("#servers_table").append(data);
					setTimeout(function() {
						$( ".newsavedserver" ).removeClass( "update" );
					}, 2500 );	
					$.getScript("/inc/fontawesome.min.js");
				}
			}					
		} );
	});
	var forward_for_var = "option forwardfor if-none\n";
	$('#forward_for').click(function() {
		if($('#optionsInput').val().indexOf(forward_for_var) == '-1') {
			$("#optionsInput").append(forward_for_var)
		} else {
			replace_text("#optionsInput", forward_for_var);
		}	
	});
	$('#forward_for1').click(function() {
		if($('#optionsInput1').val().indexOf(forward_for_var) == '-1') {
			$("#optionsInput1").append(forward_for_var)
		} else {
			replace_text("#optionsInput1", forward_for_var);
		}	
	});
	$('#forward_for2').click(function() {
		if($('#optionsInput2').val().indexOf(forward_for_var) == '-1') {
			$("#optionsInput2").append(forward_for_var)
		} else {
			replace_text("#optionsInput2", forward_for_var);
		}	
	});
	var redispatch_var = "option redispatch\n";
	$('#redispatch').click(function() {
		if($('#optionsInput').val().indexOf(redispatch_var) == '-1') {
			$("#optionsInput").append(redispatch_var)
		} else {
			replace_text("#optionsInput", redispatch_var);
		}	
	});
	$('#redispatch2').click(function() {
		if($('#optionsInput2').val().indexOf(redispatch_var) == '-1') {
			$("#optionsInput2").append(redispatch_var)
		} else {
			replace_text("#optionsInput2", redispatch_var);
		}	
	});
	var slow_atack = "option http-buffer-request\ntimeout http-request 10s\n"
	$('#slow_atack').click(function() {
		if($('#optionsInput').val().indexOf(slow_atack) == '-1') {
			$("#optionsInput").append(slow_atack)
		} else {
			replace_text("#optionsInput", slow_atack);
		}	
	});
	$('#slow_atack1').click(function() {
		if($('#optionsInput1').val().indexOf(slow_atack) == '-1') {
			$("#optionsInput1").append(slow_atack)
		} else {
			replace_text("#optionsInput1", slow_atack);
		}	
	});
	$("#ddos").checkboxradio( "disable" );
	$("#ddos1").checkboxradio( "disable" );
	$("#ddos2").checkboxradio( "disable" );
	$( "#name" ).change(function() {
		table_name = $('#name').val();
		table_name = $.trim(table_name)
		if($('#name').val() != "") {
			$("#ddos").checkboxradio( "enable" );
		} else {
			$("#ddos").checkboxradio( "disable" );
		}
	});
	$( "#new_frontend" ).change(function() {
		table_name = $('#new_frontend').val();
		table_name = $.trim(table_name)
		if($('#new_frontend').val() != "") {
			$("#ddos1").checkboxradio( "enable" );
		} else {
			$("#ddos1").checkboxradio( "disable" );
		}
	});
	
	$('#ddos').click(function() {
		if($('#name').val() == "") {
			$("#optionsInput").append(ddos_var)
		}
		var ddos_var = "#Start config for DDOS atack protect\n"+
								  "stick-table type ip size 1m expire 1m store gpc0,http_req_rate(10s),http_err_rate(10s)\n"+
								  "tcp-request connection track-sc1 src\n"+
								  "tcp-request connection reject if { sc1_get_gpc0 gt 0 }\n"+
								  "# Abuser means more than 100reqs/10s\n"+
								  "acl abuse sc1_http_req_rate("+table_name+") ge 100\n"+
								  "acl flag_abuser sc1_inc_gpc0("+table_name+")\n"+
								  "tcp-request content reject if abuse flag_abuser\n"+
								  "#End config for DDOS\n";
		if($('#optionsInput').val().indexOf(ddos_var) == '-1') {			
			if($('#name').val() == "") {
				alert("First set Listen name")
			} else {
				$("#optionsInput").append(ddos_var);
			}
		} else {
			replace_text("#optionsInput", ddos_var);
		}	
	});
	$('#ddos1').click(function() {
		if($('#new_frontend').val() == "") {
			$("#optionsInput1").append(ddos_var)
		}
		var ddos_var = "#Start config for DDOS atack protect\n"+
								  "stick-table type ip size 1m expire 1m store gpc0,http_req_rate(10s),http_err_rate(10s)\n"+
								  "tcp-request connection track-sc1 src\n"+
								  "tcp-request connection reject if { sc1_get_gpc0 gt 0 }\n"+
								  "# Abuser means more than 100reqs/10s\n"+
								  "acl abuse sc1_http_req_rate("+table_name+") ge 100\n"+
								  "acl flag_abuser sc1_inc_gpc0("+table_name+")\n"+
								  "tcp-request content reject if abuse flag_abuser\n"+
								  "#End config for DDOS\n";
		if($('#optionsInput1').val().indexOf(ddos_var) == '-1') {
			if($('#new_frontend').val() == "") {
				alert("First set Frontend name")
			} else {
				$("#optionsInput1").append(ddos_var)
			}
		} else {
			replace_text("#optionsInput1", ddos_var);
		}
	});
	var antibot_var = "#Start config for Antibot protection\n"+
		"http-request track-sc0 src table per_ip_rates\n" +
		"http-request track-sc1 url32+src table per_ip_and_url_rates unless { path_end .css .js .png .jpeg .gif }\n" +
		"acl exceeds_limit sc_gpc0_rate(0) gt 15 \n" +
		"http-request sc-inc-gpc0(0) if { sc_http_req_rate(1) eq 1 } !exceeds_limit\n" +
		"http-request deny if exceeds_limit\n" +
		"#End config for Antibot\n";
	$('#antibot').click(function() {
		if($('#optionsInput').val().indexOf(antibot_var) == '-1') {
			$("#optionsInput").append(antibot_var)
		} else {
			replace_text("#optionsInput", antibot_var);
		}
	});
	$('#antibot1').click(function() {
		if($('#optionsInput1').val().indexOf(antibot_var) == '-1') {
			$("#optionsInput1").append(antibot_var)
		} else {
			replace_text("#optionsInput1", antibot_var);
		}
	});
	$( "#blacklist_checkbox" ).click( function(){
		if ($('#blacklist_checkbox').is(':checked')) {
			$( "#blacklist-hide" ).show( "fast" );
			$( "#blacklist-hide-input" ).attr('required',true);
		} else {
			$( "#blacklist-hide" ).hide( "fast" );
			$( "#blacklist-hide-input" ).prop('required',false);
		}
	});
	$( "#blacklist_checkbox1" ).click( function(){
		if ($('#blacklist_checkbox1').is(':checked')) {
			$( "#blacklist-hide1" ).show( "fast" );
			$( "#blacklist-hide-input1" ).attr('required',true);
		} else {
			$( "#blacklist-hide1" ).hide( "fast" );
			$( "#blacklist-hide-input1" ).prop('required',false);
		}
	});
	$( "#whitelist_checkbox" ).click( function(){
		if ($('#whitelist_checkbox').is(':checked')) {
			$( "#whitelist-hide" ).show( "fast" );
			$( "#whitelist-hide-input" ).attr('required',true);
		} else {
			$( "#whitelist-hide" ).hide( "fast" );
			$( "#whitelist-hide-input" ).prop('required',false);
		}
	});
	$( "#whitelist_checkbox1" ).click( function(){
		if ($('#whitelist_checkbox1').is(':checked')) {
			$( "#whitelist-hide1" ).show( "fast" );
			$( "#whitelist-hide-input1" ).attr('required',true);
		} else {
			$( "#whitelist-hide1" ).hide( "fast" );
			$( "#whitelist-hide-input1" ).prop('required',false);
		}
	});
	$( ":regex(id, template)" ).click( function(){
		if ($(':regex(id, template)').is(':checked')) {
			$( ".prefix" ).show( "fast" );
			$( ".second-server" ).hide( "fast" );
			$( ".backend_server" ).hide( "fast" );
			$( ".send_proxy" ).hide( "fast" );
			$( "input[name=server_maxconn]" ).hide( "fast" );
			$( "input[name=port_check]" ).hide( "fast" );
			$( "[name=maxconn_name]" ).hide( "fast" );
			$( "[name=port_check_text]" ).hide( "fast" );
			$( ".prefix" ).attr('required',true);
		} else {
			$( ".prefix" ).hide( "fast" );
			$( ".prefix" ).attr('required',false);
			$( ".second-server" ).show( "fast" );
			$( ".backend_server" ).show( "fast" )
			$( ".send_proxy" ).show( "fast" )
			$( "input[name=server_maxconn]" ).show( "fast" );
			$( "input[name=port_check]" ).show( "fast" );
			$( "[name=maxconn_name]" ).show( "fast" );
			$( "[name=port_check_text]" ).show( "fast" );
		}
	});
	var location = window.location.href;
    var cur_url = '/app/' + location.split('/').pop();
	cur_url = cur_url.split('?');
	cur_url = cur_url[0].split('#');
	if (cur_url[0] == "/app/add.py") {
		$("#cache").checkboxradio( "disable" );
		$("#waf").checkboxradio( "disable" );
		$( "#serv" ).on('selectmenuchange',function() {
			change_select_acceleration("");
			change_select_waf("");
		});
		
		$("#cache2").checkboxradio( "disable" );
		$("#waf2").checkboxradio( "disable" );
		$( "#serv2" ).on('selectmenuchange',function() {
			change_select_acceleration("2");
			change_select_waf("2");
		});
			
		$("#cache3").checkboxradio( "disable" );
		$( "#serv3" ).on('selectmenuchange',function() {
			change_select_acceleration("3");
		});
		$('#compression').on( "click", function() {
			if ($('#compression').is(':checked')) {
				$("#cache").checkboxradio( "disable" );
				$("#cache").prop('checked', false);
			} else {
				change_select_acceleration("");
			}
		});
		$('#compression2').on( "click", function() {
			if ($('#compression2').is(':checked')) {
				$("#cache2").checkboxradio( "disable" );
				$("#cache2").prop('checked', false);
			} else {
				change_select_acceleration('2');
			}
		});
		$('#compression3').on( "click", function() {
			if ($('#compression3').is(':checked')) {
				$("#cache3").checkboxradio( "disable" );
				$("#cache3").prop('checked', false);
			} else {
				change_select_acceleration('3');
			}
		});
		$('#cache').on( "click", function() {
			if ($('#cache').is(':checked')) {
				$("#compression").checkboxradio( "disable" );
				$("#compression").prop('checked', false);
			} else {
				$("#compression").checkboxradio( "enable" );
			}
		});
		$('#cache2').on( "click", function() {
			if ($('#cache2').is(':checked')) {
				$("#compression2").checkboxradio( "disable" );
				$("#compression2").prop('checked', false);
			} else {
				$("#compression2").checkboxradio( "enable" );
			}
		});
		$('#cache3').on( "click", function() {
			if ($('#cache3').is(':checked')) {
				$("#compression3").checkboxradio( "disable" );
				$("#compression3").prop('checked', false);
			} else {
				$("#compression3").checkboxradio( "enable" );
			}
		});
		$( "#add1" ).on( "click", function() {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).children("#add1").css('padding-left', '30px');
				$(this).children("#add1").css('border-left', '4px solid #5D9CEB');
			});
			$( "#tabs" ).tabs( "option", "active", 0 );
		} );
		$( "#add3" ).on( "click", function() {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).children("#add3").css('padding-left', '30px');
				$(this).children("#add3").css('border-left', '4px solid #5D9CEB');
			});
			$( "#tabs" ).tabs( "option", "active", 4 );
		} );
		$( "#add4" ).on( "click", function() {
			$( "#tabs" ).tabs( "option", "active", 5 );
		} );
		$( "#add5" ).on( "click", function() {
			$( "#tabs" ).tabs( "option", "active", 6 );
		} );
		$( "#add6" ).on( "click", function() {
			$( "#tabs" ).tabs( "option", "active", 7 );
			$( "#userlist_serv" ).selectmenu( "open" );
		} );
		$( "#add7" ).on( "click", function() {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).children("#add7").css('padding-left', '30px');
				$(this).children("#add7").css('border-left', '4px solid #5D9CEB');
			});
			$( "#tabs" ).tabs( "option", "active", 9 );
		} );
	}
	
	$( "#path-cert-listen" ).autocomplete({
		source: function( request, response ) {
			if(!checkIsServerFiled('#serv2')) return false;
			$.ajax( {
				url: "options.py",
				data: {
					getcerts:1,
					serv: $("#serv").val(),
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
	$( "#path-cert-frontend" ).autocomplete({
		source: function( request, response ) {
			if(!checkIsServerFiled('#serv2')) return false;
			$.ajax( {
				url: "options.py",
				data: {
					getcerts:1,
					serv: $("#serv2").val(),
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
	$( "#ssl_key_upload" ).click(function() {
		if(!checkIsServerFiled('#serv4')) return false;
		if(!checkIsServerFiled('#ssl_name', 'Enter the Certificate name')) return false;
		if(!checkIsServerFiled('#ssl_cert', 'Paste the contents of the certificate file')) return false;
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#serv4').val(),
				ssl_cert: $('#ssl_cert').val(),
				ssl_name: $('#ssl_name').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('success') != '-1') {
					toastr.success(data);
				} else {
					toastr.error('Something wrong, check and try again');
				}
			}
		} );
	});
	$('#ssl_key_view').click(function() {
		if(!checkIsServerFiled('#serv5')) return false;
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#serv5').val(),
				getcerts: "viewcert",
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var i;
					var new_data = "";
					data = data.split("\n");
					var j = 1
					for (i = 0; i < data.length; i++) {
						data[i] = data[i].replace(/\s+/g,' ');
						if (data[i] != '') {
							if (j % 2) {
								if (j != 0) {
									new_data += '</span>'
								}
								new_data += '<span class="list_of_lists">'
							} else {
								new_data += '</span><span class="list_of_lists">'

							}
							j += 1
							new_data += ' <a onclick="view_ssl(\'' + data[i] + '\')" title="View ' + data[i] + ' cert">' + data[i] + '</a> '
						}
					}
					$("#ajax-show-ssl").html(new_data);
				} 
			}
		} );
	});
	$('#lets_button').click(function() {
		var lets_domain = $('#lets_domain').val();
		var lets_email = $('#lets_email').val();
		if (lets_email == '' || lets_domain == '') {
			toastr.error('Fields cannot be empty');
		} else if (validateEmail(lets_email)) {
			$("#ajax-ssl").html(wait_mess);
			$.ajax({
				url: "options.py",
				data: {
					serv: $('#serv_for_lets').val(),
					lets_domain: lets_domain,
					lets_email: lets_email,
					token: $('#token').val()
				},
				type: "POST",
				success: function (data) {
					if (data.indexOf('error:') != '-1' || data.indexOf('ERROR') != '-1' || data.indexOf('FAILED') != '-1') {
						toastr.clear();
						toastr.error(data);
					} else if (data.indexOf('WARNING') != '-1') {
						toastr.clear();
						toastr.warning(data);
					} else {
						toastr.clear();
						toastr.success(data);
					}
					$("#ajax-ssl").html('');
				}
			});
		} else {
			toastr.clear();
			toastr.error('Wrong e-mail format');
		}
	});
	var add_server_var = '<br /><input name="servers" title="Backend IP" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control second-server" style="margin: 2px 0 4px 0;">: ' +
		'<input name="server_port" required title="Backend port" size=3 placeholder="yyy" class="form-control second-server add_server_number" type="number"> ' +
		'port check: <input name="port_check" required title="Maxconn. Default 200" size=5 value="200" class="form-control add_server_number" type="number">' +
		' maxconn: <input name="server_maxconn" required title="Maxconn. Default 200" size=5 value="200" class="form-control add_server_number" type="number">'
	$('[name=add-server-input]').click(function() {
		$("[name=add_servers]").append(add_server_var);
		changePortCheckFromServerPort();
	});
	$('[name=port]').on('input', function (){
		var iNum = parseInt($('[name=port]').val());
		$('[name=port_check]').val(iNum);
		$('[name=server_port]').val(iNum);
	});
	changePortCheckFromServerPort();
	var add_userlist_var = '<br /><input name="userlist-user" title="User name" placeholder="user_name" class="form-control"> <input name="userlist-password" required title="User password. By default it insecure-password" placeholder="password" class="form-control"> <input name="userlist-user-group" title="User`s group" placeholder="user`s group" class="form-control">'
	$('#add-userlist-user').click(function() {
		$('#userlist-users').append(add_userlist_var);		
	});
	var add_userlist_group_var = '<br /><input name="userlist-group" title="User`s group" placeholder="group_name" class="form-control">'
	$('#add-userlist-group').click(function() {
		$('#userlist-groups').append(add_userlist_group_var);		
	});
	var add_peer_var = '<br /><input name="servers_name" required title="Peer name" size=14 placeholder="haproxyN" class="form-control">: ' +
		'<input name="servers" title="Backend IP" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control second-server">: ' +
		'<input name="server_port" required title="Backend port" size=3 placeholder="yyy" class="form-control second-server add_server_number" type="number">'
	$('[name=add-peer-input]').click(function() {
		$("[name=add_peers]").append(add_peer_var);
	});
	$('.advance-show-button').click(function() {
		$('.advance').fadeIn();
		$('.advance-show-button').css('display', 'none');
		$('.advance-hide-button').css('display', 'block');
		return false;
	});
	$('.advance-hide-button').click(function() {
		$('.advance').fadeOut();
		$('.advance-show-button').css('display', 'block');
		$('.advance-hide-button').css('display', 'none');
		return false;
	});
	$('#ssl_offloading').click(function() {
		if($('#optionsInput').val().indexOf('ssl_fc ') == '-1') {
			$("#optionsInput").append(ssl_offloading_var)
		} else {
			replace_text("#optionsInput", ssl_offloading_var);
		}
	});
	$('#ssl_offloading1').click(function() {
		if($('#optionsInput1').val().indexOf('ssl_fc ') == '-1') {
			$("#optionsInput1").append(ssl_offloading_var)
		} else {
			replace_text("#optionsInput1", ssl_offloading_var);
		}

	});
	$('#ssl_offloading2').click(function() {
		if($('#optionsInput2').val().indexOf('ssl_fc ') == '-1') {
			$("#optionsInput2").append(ssl_offloading_var)
		} else {
			replace_text("#optionsInput2", ssl_offloading_var);
		}
	});
	
	$( ".redirectListen" ).on( "click", function() {
		resetProxySettings();
		$( "#tabs" ).tabs( "option", "active", 1 );
		$( "#serv" ).selectmenu( "open" );
	} );
	$( ".redirectFrontend" ).on( "click", function() {
		resetProxySettings();
		var TabId = 2;
		$( "#tabs" ).tabs( "option", "active", TabId );
		$( "#serv"+TabId ).selectmenu( "open" );
	} );
	$( ".redirectBackend" ).on( "click", function() {
		resetProxySettings();
		var TabId = 3;
		$( "#tabs" ).tabs( "option", "active", TabId );
		$( "#serv"+TabId ).selectmenu( "open" );
	} );
	$( ".redirectSsl" ).on( "click", function() {
		$( "#tabs" ).tabs( "option", "active", 4 );
		$( "#serv5" ).selectmenu( "open" );
	} );
	
	$( "#create-http-listen" ).on( "click", function() {
		resetProxySettings();
		createHttp(1, 'listen');
	});
	$( "#create-http-frontend" ).on( "click", function() {
		resetProxySettings();
		createHttp(2, 'frontend');
	});
	$( "#create-http-backend" ).on( "click", function() {
		resetProxySettings();
		createHttp(3, 'backend');
	});
	$( "#create-ssl-listen" ).on( "click", function() {
		resetProxySettings();
		createSsl(1, 'listen');
	});
	$( "#create-ssl-frontend" ).on( "click", function() {
		resetProxySettings();
		createSsl(2, 'frontend');
	});
	$( "#create-ssl-backend" ).on( "click", function() {
		resetProxySettings();
		createSsl(3, 'backend');
	});
	$( "#create-https-listen" ).on( "click", function() {
		resetProxySettings();
		createHttps(1, 'listen'); 
	});
	$( "#create-https-frontend" ).on( "click", function() {
		resetProxySettings();
		createHttps(2, 'frontend');		
	});
	$( "#create-https-backend" ).on( "click", function() {
		resetProxySettings();
		createHttps(3, 'backend');	
	});
	var tcp_note = 'The check is valid when the server answers with a <b>SYN/ACK</b> packet'
	var ssl_note = 'The check is valid if the server answers with a valid SSL server <b>hello</b> message'
	var httpchk_note = 'The check is valid if the server answers with a status code of <b>2xx</b> or <b>3xx</b>. You can ' +
		'add a page for checking and Domain name'
	var ldap_note = 'The check is valid if the server response contains a successful <b>resultCode</b>.\n' +
		'<p>You must configure the LDAP servers according to this check to allow anonymous binding. ' +
		'You can do this with an IP alias on the server side that allows only HAProxy IP addresses to bind to it.</p>'
	var mysql_note = 'The check is valid if the server response contains a successful <b>Authentication</b> request'
	var pgsql_note = 'The check is valid if the server response contains a successful <b>Authentication</b> request'
	var redis_note = 'The check is valid if the server response contains the string <b>+PONG</b>'
	var smtpchk_note = 'The check is valid if the server response code starts with <b>\'2\'</b>'
	$( "#listener_checks" ).on('selectmenuchange',function()  {
		if ($( "#listener_checks option:selected" ).val() == "option tcp-check") {
			$("#listener_checks_note").html(tcp_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option ssl-hello-chk") {
			$("#listener_checks_note").html(ssl_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option httpchk") {
			$("#listener_checks_note").html(httpchk_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option ldap-check") {
			$("#listener_checks_note").html(ldap_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option mysql-check") {
			$("#listener_checks_note").html(mysql_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option pgsql-check") {
			$("#listener_checks_note").html(pgsql_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option redis-check") {
			$("#listener_checks_note").html(redis_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "option smtpchk") {
			$("#listener_checks_note").html(smtpchk_note)
		}
		if ($( "#listener_checks option:selected" ).val() == "") {
			$("#listener_checks_note").html('')
		}
	});
	$( "#backend_checks" ).on('selectmenuchange',function()  {
		if ($( "#backend_checks option:selected" ).val() == "") {
			$("#backend_checks_note").html('')
		}
		if ($( "#backend_checks option:selected" ).val() == "option tcp-check") {
			$("#backend_checks_note").html(tcp_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option ssl-hello-chk") {
			$("#backend_checks_note").html(ssl_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option httpchk") {
			$("#backend_checks_note").html(httpchk_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option ldap-check") {
			$("#backend_checks_note").html(ldap_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option mysql-check") {
			$("#backend_checks_note").html(mysql_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option pgsql-check") {
			$("#backend_checks_note").html(pgsql_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option redis-check") {
			$("#backend_checks_note").html(redis_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "option smtpchk") {
			$("#backend_checks_note").html(smtpchk_note)
		}
		if ($( "#backend_checks option:selected" ).val() == "") {
			$("#backend_checks_note").html('')
		}
	});
	$( "#listener_checks" ).on('selectmenuchange',function() {
		if ($("#listener_checks").val() == 'option httpchk') {
			$("#listener_checks_http").show();
			$("#listener_checks_http_path").attr('required', 'true');
		} else {
			$("#listener_checks_http").hide();
			$("#listener_checks_http_path").removeAttr('required');
			$("#listener_checks_http_domain").removeAttr('required');
		}
	});
	$( "#backend_checks" ).on('selectmenuchange',function() {
		if ($("#backend_checks").val() == 'option httpchk') {
			$("#backend_checks_http").show();
			$("#backend_checks_http_path").attr('required', 'true');
		} else {
			$("#backend_checks_http").hide();
			$("#backend_checks_http_path").removeAttr('required');
			$("#backend_checks_http_domain").removeAttr('required');
		}
	});
	$( "#add_listener_acl" ).on( "click", function() {
		$( "#listener_acl" ).show();
		$( "#listener_add_acl" ).show();
		$( "#add_listener_acl" ).hide();
	} );
	$( "#add_frontend_acl" ).on( "click", function() {
		$( "#frontend_acl" ).show();
		$( "#frontend_add_acl" ).show();
		$( "#add_frontend_acl" ).hide();
	} );
	$( "#add_backend_acl" ).on( "click", function() {
		$( "#backend_acl" ).show();
		$( "#backend_add_acl" ).show();
		$( "#add_backend_acl" ).hide();
	} );
	$("#listener_add_acl").click(function(){
		make_actions_for_adding_acl_rule('#listener_acl');
		$("#listener_acl").find('option[value=5]').remove();
	});
	$("#frontend_add_acl").click(function(){
		make_actions_for_adding_acl_rule('#frontend_acl');
	});
	$("#backend_add_acl").click(function(){
		make_actions_for_adding_acl_rule('#backend_acl');
	});
	$("#add_bind_listener").click(function(){
		make_actions_for_adding_bind('#listener_bind');
		$( "#listener_bind" ).show();
	});
	$("#add_bind_frontend").click(function(){
		make_actions_for_adding_bind('#frontend_bind');
		$( "#frontend_bind" ).show();
	});
	$( "#serv" ).on('selectmenuchange',function() {
		$('#name').focus();
	});
	$( "#serv2" ).on('selectmenuchange',function() {
		$('#new_frontend').focus();
	});
	$( "#serv3" ).on('selectmenuchange',function() {
		$('#new_backend').focus();
	});
	$( "#userlist_serv" ).on('selectmenuchange',function() {
		$('#new_userlist').focus();
	});
});
function resetProxySettings() {
	$('[name=ip]').val('');
	$('[name=port]').val('');
	$('[name=server_port]').val('');
	$('input:checkbox').prop( "checked", false );
	$('[name=ssl-check]').prop( "checked", true );
	$('[name=ssl-dis-check]').prop( "checked", false );
	$('[name=check-servers]').prop( "checked", true );
	$('input:checkbox').checkboxradio("refresh");
	$('.advance-show').fadeIn();
	$('.advance').fadeOut();
	$('[id^=https-hide]').hide();
	$('[name=mode').val('http');
	$('select').selectmenu('refresh');
	$("#path-cert-listen" ).attr('required',false);
	$("#path-cert-frontend" ).attr('required',false);
	replace_text("#optionsInput", ssl_offloading_var);
	replace_text("#optionsInput1", ssl_offloading_var);
	replace_text("#optionsInput2", ssl_offloading_var);
}
function createHttp(TabId, proxy) {
	$('[name=port]').val('80');
	$('[name=server_port]').val('80');
	$( "#tabs" ).tabs( "option", "active", TabId );
	if (TabId == 1) {
		TabId = '';
	}
	$( "#serv"+TabId ).selectmenu( "open" );
	history.pushState('Add '+proxy, 'Add '+proxy, 'add.py#'+proxy)
}
function createSsl(TabId, proxy) {
	$('[name=port]').val('443');
	$('[name=server_port]').val('80');
	$('.advance-show').fadeOut();
	$('.advance').fadeIn()
	$( "#tabs" ).tabs( "option", "active", TabId );
	$( "#https-hide-"+proxy).show("fast");
	$('#https-'+proxy).prop( "checked", true );
	$('#ssl-dis-check-'+proxy).prop( "checked", true );
	$('#ssl-check-'+proxy).prop( "checked", false );
	$('#ssl-check-'+proxy).checkboxradio('disable');
	$('input:checkbox').checkboxradio("refresh");
	$("#path-cert-"+proxy ).attr('required',true);
	if (TabId == 1) {
		TabId = '';
	}
	$( "#serv"+TabId ).selectmenu( "open" );
	history.pushState('Add'+proxy, 'Add'+proxy, 'add.py#'+proxy)
}
function createHttps(TabId, proxy) {
	$('[name=port]').val('443');
	$('[name=server_port]').val('443');
	$('.advance-show').fadeOut();
	$('.advance').fadeIn();
	$( "#tabs" ).tabs( "option", "active", TabId );
	$('#'+proxy+'-mode-select').val('tcp');
	$('#'+proxy+'-mode-select').selectmenu('refresh');
	if (TabId == 1) {
		TabId = '';
	}
	$( "#serv"+TabId ).selectmenu( "open" );
	history.pushState('Add'+proxy, 'Add'+proxy, 'add.py#'+proxy)
}
function confirmDeleteOption(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#option-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeOption(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function removeOption(id) {
	$("#option-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			optiondel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#option-"+id).remove();
			}
		}					
	} );
}
function updateOptions(id) {
	toastr.clear();
	$.ajax( {
		url: "options.py",
		data: {
			updateoption: $('#option-body-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#option-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#option-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function confirmDeleteSavedServer(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#servers-saved-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );	
			removeSavedServer(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function removeSavedServer(id) {
	$("#servers-saved-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			savedserverdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data.indexOf('Ok') != '-1') {
				$("#servers-saved-"+id).remove();
			}
		}					
	} );
}
function updateSavedServer(id) {
	toastr.clear();
	$.ajax( {
		url: "options.py",
		data: {
			updatesavedserver: $('#servers-ip-'+id).val(),
			description: $('#servers-desc-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#option-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#option-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function view_ssl(id) {
	if(!checkIsServerFiled('#serv5')) return false;
	$.ajax( {
		url: "options.py",
		data: {
			serv: $('#serv5').val(),
			getcert: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$( "#dialog-confirm-cert" ).dialog({
					resizable: false,
					height: "auto",
					width: 670,
					modal: true,
					title: "Certificate from "+$('#serv5').val()+", name: "+id,
					buttons: {
						Close: function() {
							$( this ).dialog( "close" );
						},
						Delete: function () {
							$( this ).dialog( "close" );
							confirmDeleting("SSL cert", id, $( this ), "");
						}
					  }
				});					
			} 
		}
	} );
}
function deleteSsl(id) {
	if(!checkIsServerFiled('#serv5')) return false;;
	$.ajax( {
		url: "options.py",
		data: {
			serv: $('#serv5').val(),
			delcert: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				toastr.success('SSL cert ' + id + ' has been deleted');
				$("#ssl_key_view").trigger( "click" );
			}
		}
	} );
}
function change_select_acceleration(id) {
	$.ajax( {
		url: "options.py",
		data: {
			get_hap_v: 1,
			serv: $('#serv'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(parseFloat(data) < parseFloat('1.8') || data == ' ') {
				$("#cache"+id).checkboxradio( "disable" );
			} else {
				$("#cache"+id).checkboxradio( "enable" );
			}
		}
	} );
}
function change_select_waf(id) {
	$.ajax( {
		url: "options.py",
		data: {
			get_hap_v: 1,
			serv: $('#serv'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {	
			if(parseFloat(data) < parseFloat('1.8')) {	
				$("#waf"+id).checkboxradio( "disable" );
			} else {
				$("#waf"+id).checkboxradio( "enable" );
			}
		}
	} );
}
function createList(color) {
	if(color == 'white') {
		list = $('#new_whitelist_name').val() 
	} else {
		list = $('#new_blacklist_name').val()
	}
	list = escapeHtml(list);
	$.ajax( {
		url: "options.py",
		data: {
			bwlists_create: list,
			color: color,
			group: $('#group').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1' || data.indexOf('Errno') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('Info') != '-1' ){
				toastr.clear();
				toastr.info(data);
			} else if (data.indexOf('success') != '-1' ) {
				toastr.clear();
				toastr.success('List has been created');
				setTimeout(function () {
					location.reload();
				}, 2500);
			}
		}
	} );	
}
function editList(list, color) {
	$.ajax( {
		url: "options.py",
		data: {
			bwlists: list,
			color: color,
			group: $('#group').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#edit_lists').text(data);
				$( "#dialog-confirm-cert-edit" ).dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Edit "+color+" list "+list,
					buttons: {
						"Delete": function() {
							$( this ).dialog( "close" );
							confirmDeleting('list', list, $( this ), color);
						},
						"Just save": function() {
							$( this ).dialog( "close" );	
							saveList('save', list, color);
						},
						"Save and reload": function() {
							$( this ).dialog( "close" );	
							saveList('reload', list, color);
						},
						"Save and restart": function() {
							$( this ).dialog( "close" );	
							saveList('restart', list, color);
						},
						Cancel: function() {
							$( this ).dialog( "close" );
						}
					  }
				});					
			} 
		}
	} );	
}
function saveList(action, list, color) {
	var serv = $( "#serv-"+color+"-list option:selected" ).val();
	if (serv == '------') {
		toastr.warning('Select a server before updating');
	} else {
		$.ajax({
			url: "options.py",
			data: {
				bwlists_save: list,
				serv: serv,
				bwlists_content: $('#edit_lists').val(),
				color: color,
				group: $('#group').val(),
				bwlists_restart: action,
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.split(" , ");

				for (i = 0; i < data.length; i++) {
					if (data[i]) {
						if (data[i].indexOf('error: ') != '-1' || data[i].indexOf('Errno') != '-1') {
							toastr.error(data[i]);
						} else {
							toastr.success(data[i]);
						}
					}
				}
			}
		});
	}
}
function deleteList(list, color) {
	var serv = $( "#serv-"+color+"-list option:selected" ).val();
	if (serv == 'Choose server') {
		toastr.warning('Choose a server before deleting');
	} else {
		$.ajax({
			url: "options.py",
			data: {
				bwlists_delete: list,
				serv: serv,
				color: color,
				group: $('#group').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1' || data.indexOf('Errno') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('success') != '-1' ) {
					toastr.clear();
					toastr.success('List has been deleted');
					setTimeout(function () {
						location.reload();
					}, 2500);
				}
			}
		});
	}
}
function generateConfig(form_name) {
	var frm = $('#'+form_name);
	if (form_name == 'add-listener') {
		serv = '#serv'
		name_id = '#name'
	} else if (form_name == 'add-frontend') {
		serv = '#serv2'
		name_id = '#new_frontend'
	} else if (form_name == 'add-backend') {
		serv = '#serv3'
		name_id = '#new_backend'
	} else if (form_name == 'add-userlist') {
		serv = '#userlist_serv'
		name_id = '#new_userlist'
	} else {
		serv = '#peers_serv'
		name_id = '#peers-name'
	}
	if(!checkIsServerFiled(serv)) return false;
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	var input = $("<input>")
		.attr("name", "generateconfig").val("1").attr("type", "hidden").attr("id", "generateconfig");
	$('#'+form_name +' input[name=acl_then_value]').each(function(){
		if (!$(this).val()){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=ip]').each(function(){
		if (!$(this).val()){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if (!$(this).val()){
			$(this).val('IsEmptY')
		}
	});
	frm.append(input);
	$.ajax({
		url: frm.attr('action'),
		data: frm.serialize(),
		type: frm.attr('method'),
		success: function (data) {
			if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1') {
				toastr.clear();
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$("#dialog-confirm-cert").dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Generated config",
					buttons: {
						Ok: function () {
							$(this).dialog("close");
						}
					}
				});
			}
		}
	});
	$("#generateconfig").remove();
	$('#'+form_name +' input[name=acl_then_value]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
		$('#'+form_name +' input[name=ip]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
}
function addProxy(form_name) {
	var frm = $('#'+form_name);
	if (form_name == 'add-listener') {
		serv = '#serv'
		name_id = '#name'
	} else if (form_name == 'add-frontend') {
		serv = '#serv2'
		name_id = '#new_frontend'
	} else if (form_name == 'add-backend') {
		serv = '#serv3'
		name_id = '#new_backend'
	} else if (form_name == 'add-userlist') {
		serv = '#userlist_serv'
		name_id = '#new_userlist'
	} else {
		serv = '#peers_serv'
		name_id = '#peers-name'
	}
	if(!checkIsServerFiled(serv)) return false;
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	$('#'+form_name +' input[name=acl_then_value]').each(function(){
		if ($(this).val().length === 0){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=ip]').each(function(){
		if ($(this).val().length === 0){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if ($(this).val().length === 0){
			$(this).val('IsEmptY')
		}
	});
	$.ajax({
		url: frm.attr('action'),
		data: frm.serialize(),
		type: frm.attr('method'),
		success: function( data ) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1') {
				toastr.clear();
				toastr.error(data);
			} else if (data == '') {
				toastr.clear();
				toastr.error('error: Proxy cannot be empty');
			} else {
				toastr.clear();
				toastr.success('Section: <b>' + data + '</b> has been added. Do not forget to restart the server');
				var ip = frm.find('select[name=serv]').val();
				localStorage.setItem('restart', ip);
				resetProxySettings();
			}
		}
	});
	$('#'+form_name +' input[name=acl_then_value]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
	$('#'+form_name +' input[name=ip]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
}
function confirmDeleting(deleting_thing, id, dialog_id, color) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: "Are you sure you want to delete this " + deleting_thing + " " +id + "?",
		buttons: {
			"Delete": function() {
				if (deleting_thing == "SSL cert") {
					deleteSsl(id);
					$(dialog_id).dialog( "close" );
				} else if (deleting_thing == "list") {
					deleteList(id, color);
					$(dialog_id).dialog( "close" );
				}
				$( this ).dialog( "close" );
			},
			Cancel: function() {
				$( this ).dialog( "close" );
				$(dialog_id).dialog( "open" );
			}
		}
	});
}
function deleteId(id) {
	$('#'+id).remove();
	if ($('#listener_bind  > p').length == 0) {
		$('#listener_bind').hide();
	}
	if ($('#frontend_bind  > p').length == 0) {
		$('#frontend_bind').hide();
	}
}
var acl_option = '<p id="new_acl_p" style="border-bottom: 1px solid #ddd; padding-bottom: 10px;">\n' +
		'<b class="padding10">if</b>\n' +
		'<select name="acl_if">\n' +
		'\t<option selected>Choose if</option>\n' +
		'\t<option value="1">Host name starts with</option>\n' +
		'\t<option value="2">Host name ends with</option>\n' +
		'\t<option value="3">Path starts with</option>\n' +
		'\t<option value="4">Path ends with</option>\n' +
		'\t<option value="6">Src ip</option>\n' +
		'</select> ' +
		'<b class="padding10">value</b>\n' +
		'<input type="text" name="acl_value" class="form-control">\n' +
		'<b class="padding10">then</b>\n' +
		'<select name="acl_then">\n' +
		'\t<option selected>Choose then</option>\n' +
		'\t<option value="5">Use backend</option>\n' +
		'\t<option value="2">Redirect to</option>\n' +
		'\t<option value="3">Allow</option>\n' +
		'\t<option value="4">Deny</option>\n' +
		'\t<option value="6">Return</option>\n' +
		'\t<option value="7">Set-header</option>\n' +
		'</select>\n' +
		'<b class="padding10">value</b>\n' +
		'<input type="text" name="acl_then_value" class="form-control" value="" title="Required if \"then\" is \"Use backend\" or \"Redirect\"">\n' +
		'<span class="minus minus-style" id="new_acl_rule_minus" title="Delete this ACL"></span>' +
		'</p>'
function make_actions_for_adding_acl_rule(section_id) {
	var random_id = makeid(3);
	$(section_id).append(acl_option);
	$('#new_acl_rule_minus').attr('onclick', 'deleteId(\''+random_id+'\')');
	$('#new_acl_rule_minus').attr('id', '');
	$('#new_acl_p').attr('id', random_id);
	$('#new_acl_rule_minus').attr('id', '');
	$.getScript("/inc/fontawesome.min.js");
	$( "select" ).selectmenu();
	$('[name=acl_if]').selectmenu({width: 180});
	$('[name=acl_then]').selectmenu({width: 180});
}
var bind_option = '<p id="new_bind_p"><input type="text" name="ip" size="15" placeholder="Any" class="form-control ui-autocomplete-input" autocomplete="off">' +
	'<b>:</b> ' +
	'<input type="text" name="port" size="5" style="" required="" placeholder="8080" title="Port for bind listen" class="form-control" autocomplete="off"> ' +
	'<span class="minus minus-style" id="new_bind_minus" title="Remove the IP-port pair"></span>'
function make_actions_for_adding_bind(section_id) {
	var random_id = makeid(3);
	$(section_id).append(bind_option);
	$('#new_bind_minus').attr('onclick', 'deleteId(\''+random_id+'\')');
	$('#new_bind_minus').attr('id', '');
	$('#new_bind_p').attr('id', random_id);
	$('#new_bind_minus').attr('id', '');
	$.getScript("/inc/fontawesome.min.js");
	$( "select" ).selectmenu();
	var serv = 'serv2'
	if(section_id == '#listener_bind') {
		serv = 'serv'
	}
	$( "#"+random_id + " > input[name=ip]").autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					show_ip: request.term,
					serv: $("#"+serv).val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}
			} );
		},
		autoFocus: true,
		minLength: -1,
		select: function( event, ui ) {
			$( "#"+random_id + " > input[name=port]").focus();
		}
	});
}
function makeid(length) {
   var result           = '';
   var characters       = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
   var charactersLength = characters.length;
   for ( var i = 0; i < length; i++ ) {
      result += characters.charAt(Math.floor(Math.random() * charactersLength));
   }
   return result;
}
function showUserlists() {
	var serv = $( "#existing_userlist_serv option:selected" ).val();
	if (serv == 'Choose server') {
		toastr.warning('Choose a server before');
	} else {
		$.ajax({
			url: "options.py",
			data: {
				show_userlists: 1,
				serv: serv,
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
					toastr.error(data);
				} else {
					$('#existing_userlist_tr').show();
					$('#existing_userlist_ajax').text('');
					data = data.split(",");
					for (i = 0; i < data.length; i++) {
						$('#existing_userlist_ajax').append('<a href="sections.py?serv='+serv+'&section='+data[i]+'" title="Edit/Delete this userlist" target="_blank">'+data[i]+'</a> ');
					}
				}
			}
		});
	}
}
function changePortCheckFromServerPort() {
	$('[name=server_port]').on('input', function (){
		var iNum = parseInt($($(this)).val());
		$($(this)).next().val(iNum);
	});
}
function checkIsServerFiled(select_id, message = 'Choose the server first') {
	if ($(select_id).val() == null || $(select_id).val() == '') {
		toastr.warning(message);
		return false;
	}
	return true;
}