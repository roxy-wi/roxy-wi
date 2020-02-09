var ssl_offloading_var = "http-request set-header X-Forwarded-Port %[dst_port] \n"+
						"http-request add-header X-Forwarded-Proto https if { ssl_fc } \n"+
						"redirect scheme https if !{ ssl_fc } \n"
$( function() {	
	$('#close').click(function(){
		$('.alert-success').remove();
		$('.alert-danger').remove();
	});
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
		"acl", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "set cookie", "dynamic-cookie-key", "mysql-check", "tcpka", "tcplog", "forwardfor", "option"
	];
			
	$( "#ip" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					ip: request.term,
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
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					ip: request.term,
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
			$(this).next().next().focus();				
		}
	});
	$( "#backends" ).autocomplete({
		source: function( request, response ) {
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
			$("#options").empty();
		}
	});
	$( "#saved-options" ).autocomplete({
		dataType: "json",
		source: "sql.py?getoption="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$("#optionsInput").append(ui.item.value + " \n");
			$(this).val('');	
			$(this).autocomplete( "close" );
		}
	});
	$( "#options1" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput1").append(ui.item.value + " ")
		}
	});
	$( "#saved-options1" ).autocomplete({
		dataType: "json",
		source: "sql.py?getoption="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$("#optionsInput1").append(ui.item.value + " \n");	
			$(this).val('');	
			$(this).autocomplete( "close" );		
		}
	});
	$( "#options2" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput2").append(ui.item.value + " ")
		}
	});
	$( "#saved-options2" ).autocomplete({
		dataType: "json",
		source: "sql.py?getoption="+$('#group').val()+'&token='+$('#token').val(),
		autoFocus: true,
	    minLength: 1,
		select: function( event, ui ) {
			$("#optionsInput2").append(ui.item.value + " \n");	
			$(this).val('');	
			$(this).autocomplete( "close" );	
		}
	});
	$('#add-option-button').click(function() {
		if ($('#option-add-table').css('display', 'none')) {
			$('#option-add-table').show("blind", "fast");
		} 
	});
	$('#add-option-new').click(function() {
		$('#error').remove();	
		$('.alert-danger').remove();	
		$.ajax( {
			
			url: "sql.py",
			data: {
				newtoption: $('#new-option').val(),
				newoptiongroup: $('#group').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-option").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
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
		source: "sql.py?getsavedserver="+$('#group').val()+'&token='+$('#token').val(),
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
		$('#error').remove();	
		$('.alert-danger').remove();	
		$.ajax( {
			
			url: "sql.py",
			data: {
				newsavedserver: $('#new-saved-servers').val(),
				newsavedservergroup: $('#group').val(),
				newsavedserverdesc: $('#new-saved-servers-description').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error') != '-1') {
					$("#ajax-option").append(data);
					$('#errorMess').click(function() {
						$('#error').remove();
						$('.alert-danger').remove();
					});
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
		var ddos_var = "#Start config for DDOS atack protecte\n"+
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
		var ddos_var = "#Start config for DDOS atack protecte\n"+
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
	$( ":regex(id, template)" ).click( function(){
		if ($(':regex(id, template)').is(':checked')) {
			$( ".prefix" ).show( "fast" );
			$( ".second-server" ).hide( "fast" );
			$( ".add-server" ).hide( "fast" );
			$( ".prefix" ).attr('required',true);
		} else {
			$( ".prefix" ).hide( "fast" );
			$( ".prefix" ).attr('required',false);
			$( ".second-server" ).show( "fast" );
			$( ".add-server" ).show( "fast" )
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
		} );
		$( "#add7" ).on( "click", function() {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).children("#add7").css('padding-left', '30px');
				$(this).children("#add7").css('border-left', '4px solid #5D9CEB');
			});
			$( "#tabs" ).tabs( "option", "active", 8 );
		} );
	}
	
	$( "#path-cert-listen" ).autocomplete({
		source: function( request, response ) {
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
		$('.alert-danger').remove();
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
				if (data.indexOf('danger') != '-1') {
					$("#ajax-ssl").html(data);
				} else if (data.indexOf('success') != '-1') {
					$('.alert-danger').remove();
					$( "#ajax-ssl").html(data);
				} else {
					$("#ajax-ssl").html('<div class="alert alert-danger">Something wrong, check and try again</div>');
				}
			}
		} );
	});
	$('#ssl_key_view').click(function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#serv5').val(),
				getcerts: "viewcert",
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('danger') != '-1') {
					$("#ajax-show-ssl").html(data);
				} else {
					$('.alert-danger').remove();
					var i;
					var new_data = "";
					data = data.split("\n");
					
					for (i = 0; i < data.length; i++) {
						data[i] = data[i].replace(/\s+/g,' ');
						new_data += ' <a onclick="view_ssl(\''+data[i]+'\')" style="cursor: pointer;" title="View this cert">'+data[i]+'</a> '
					}
					$("#ajax-show-ssl").html("<b>"+new_data+"</b>");					
				} 
			}
		} );
	});
	var add_server_var = '<br /><input name="servers" title="Backend IP" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control">: <input name="server_port" title="Backend port" size=1 placeholder="yyy" class="form-control">'
	$('[name=add-server-input]').click(function() {
		$("[name=add_servers]").append(add_server_var);			
	});
	var add_userlist_var = '<br /><input name="userlist-user" title="User name" placeholder="user_name" class="form-control"> <input name="userlist-password" required title="User password. By default it insecure-password" placeholder="password" class="form-control"> <input name="userlist-user-group" title="User`s group" placeholder="user`s group" class="form-control">'
	$('#add-userlist-user').click(function() {
		$('#userlist-users').append(add_userlist_var);		
	});
	var add_userlist_group_var = '<br /><input name="userlist-group" title="User`s group" placeholder="group_name" class="form-control">'
	$('#add-userlist-group').click(function() {
		$('#userlist-groups').append(add_userlist_group_var);		
	});
	$('.advance-show').click(function() {
		$('.advance-show').fadeOut();
		$('.advance').fadeIn();
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
		resetProxySettings()
		$( "#tabs" ).tabs( "option", "active", 1 );
	} );
	$( ".redirectFrontend" ).on( "click", function() {
		resetProxySettings()
		$( "#tabs" ).tabs( "option", "active", 2 );
	} );
	$( ".redirectBackend" ).on( "click", function() {
		resetProxySettings()
		$( "#tabs" ).tabs( "option", "active", 3 );
	} );
	$( ".redirectSsl" ).on( "click", function() {
		$( "#tabs" ).tabs( "option", "active", 4 );
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
		$('#ssl_offloading').prop( "checked", true );
		$('#ssl_offloading').checkboxradio("refresh")
		$("#optionsInput").append(ssl_offloading_var)
	});
	$( "#create-ssl-frontend" ).on( "click", function() {
		resetProxySettings();
		createSsl(2, 'frontend');	
		$('#ssl_offloading1').prop( "checked", true );
		$('#ssl_offloading1').checkboxradio("refresh")	
		$("#optionsInput1").append(ssl_offloading_var)		
	});
	$( "#create-ssl-backend" ).on( "click", function() {
		resetProxySettings();
		createSsl(3, 'backend');	
		$('#ssl_offloading2').prop( "checked", true );
		$('#ssl_offloading2').checkboxradio("refresh");
		$("#optionsInput2").append(ssl_offloading_var);
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
});
function resetProxySettings() {
	$('[name=port]').val('');
	$('[name=server_port]').val('');
	$('input:checkbox').prop( "checked", false );
	$('[name=ssl-check]').prop( "checked", true );
	$('[name=check-servers]').prop( "checked", true );
	$('input:checkbox').checkboxradio("refresh");
	$('.advance-show').fadeIn();
	$('.advance').fadeOut();
	$('[id^=https-hide]').hide();
	$('[name=mode').val('http');
	$('select').selectmenu('refresh');
	replace_text("#optionsInput", ssl_offloading_var);
	replace_text("#optionsInput1", ssl_offloading_var);
	replace_text("#optionsInput2", ssl_offloading_var);
}
function createHttp(TabId, proxy) {
	$('[name=port]').val('80');
	$('[name=server_port]').val('80');
	$( "#tabs" ).tabs( "option", "active", TabId );	
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
	$('#https-'+proxy).checkboxradio("refresh")
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
		url: "sql.py",
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
	$('#error').remove();	
	$.ajax( {
		url: "sql.py",
		data: {
			updateoption: $('#option-body-'+id).val(),
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
		url: "sql.py",
		data: {
			savedserverdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#servers-saved-"+id).remove();
			}
		}					
	} );
}
function updateSavedServer(id) {
	$('#error').remove();	
	$.ajax( {
		url: "sql.py",
		data: {
			updatesavedserver: $('#servers-ip-'+id).val(),
			description: $('#servers-desc-'+id).val(),
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
				$("#option-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#option-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function view_ssl(id) {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $('#serv5').val(),
			getcert: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('danger') != '-1') {
				$("#ajax-show-ssl").html(data);
			} else {
				$('.alert-danger').remove();
				$('#dialog-confirm-body').text(data);
				$( "#dialog-confirm-cert" ).dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Certificate from "+$('#serv5').val()+", name: "+id,
					buttons: {
						Ok: function() {
							$( this ).dialog( "close" );
						}
					  }
				});					
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
			if(parseFloat(data) < parseFloat('1.8')) {	
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
			$("#ajax").html(data); 
			setTimeout(function() {
						location.reload();
					}, 2500 );			 
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
			if (data.indexOf('danger') != '-1') {
				$("#ajax").html(data);
			} else {
				$('.alert-danger').remove();
				$('#edit_lists').text(data);
				$( "#dialog-confirm-cert-edit" ).dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Edit "+color+" list "+list,
					buttons: {
						"Just save": function() {
							$( this ).dialog( "close" );	
							saveList('save', list, color);
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
	$.ajax( {
		url: "options.py",
		data: {
			bwlists_save: list,
			bwlists_content: $('#edit_lists').val(),
			color: color,
			group: $('#group').val(),
			bwlists_restart: action,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data); 
		}
	} );	
}