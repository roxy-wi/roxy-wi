$( function() {
	$( "#tabs" ).tabs();
	$( "#redirectBackend" ).on( "click", function() {
		$( "#tabs" ).tabs( "option", "active", 2 );
	} );
	$( "select" ).selectmenu();
	$( document ).tooltip();
	$( "input[type=submit], button" ).button();
} );

$( function() {
	var availableTags = [
		"acl", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "tcpka", "tcplog", "forwardfor", "option"
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
					serv: $("#serv").val()
				},
				success: function( data ) {
					response(data.split("\n"));
				}					
			} );
		},
		autoFocus: true,
		minLength: -1
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
					serv: $("#serv").val()
				},
				success: function( data ) {
					response(data.split("\n"));
					}					
			} );
		},
		autoFocus: true,
		minLength: -1
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
					serv: $("#serv2").val()
				},
				success: function( data ) {
					response(data.split('"'));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
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
	$( "#options1" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput1").append(ui.item.value + " ");				
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
} );