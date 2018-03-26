$( function() {
	$( "#tabs" ).tabs();
	$( "#redirectBackend" ).on( "click", function() {
		$( "#tabs" ).tabs( "option", "active", 2 );
	} );
	$( "select" ).selectmenu();
		
    var tooltips = $( "[title]" ).tooltip({
      position: {
        my: "left top",
        at: "right+5 top-25",
        collision: "none"
      }
    });
	$( "input[type=submit], button" ).button();
	$( "input[type=checkbox]" ).checkboxradio();
	$( "#number" ).spinner();
	$( ".controlgroup" ).controlgroup();
	$( ".configShow" ).accordion({
      collapsible: true,
	  heightStyle: "content",
	  icons: { "header": "ui-icon-plus", "activeHeader": "ui-icon-minus" }
    });
	$('#select_all').click(function(){
        var checkboxes = $(this).closest('form').find(':checkbox');
        if($(this).prop('checked')) {
          $("form input[type='checkbox']").attr("checked",true).change();
		  $("#label_select_all").text("Unselect all");
        } else {
          $("form input[type='checkbox']").attr("checked",false).change();
		  $("#label_select_all").text("Select all");
        }
    });
	$ ( "#show-all-users" ).click( function() {
		if($( "#show-all-users" ).text() == "Show all") {
			$( ".show-users" ).show("fast");
			$( "#show-all-users" ).text("Hide");
			$( "show-all-users" ).attr("title") = "Hide all users";
		} else {
			$( ".show-users" ).hide("fast");
			$( "#show-all-users" ).attr("title", "Show all users");
			$( "#show-all-users" ).text("Show all");
		}
	});
	$( "#listen-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#listen-mode-select option:selected" ).val() == "tcp") {
			$( "#https-listen-span" ).hide("fast");
			$( "#https-hide-listen" ).hide("fast");
			$( "#https-listen" ).prop("checked", false);
		} else {
			$( "#https-listen-span" ).show("fast");
		}
	});
	$( "#frontend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#frontend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-frontend-span" ).hide("fast");
			$( "#https-hide-frontend" ).hide("fast");
		} else {
			$( "#https-frontend-span" ).show("fast");
		}
	});
	$( "#backend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#backend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-backend-span" ).hide("fast");
			$( "#https-hide-backend" ).hide("fast");
		} else {
			$( "#https-backend-span" ).show("fast");
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
			$( "#path-cert-backend" ).attr('required',true);
		} else {
			$( "#https-hide-backend" ).hide( "fast" );
			$( "#path-cert-backend" ).prop('required',false);
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
	$( "#hide_menu" ).click(function() {
		if ($(".top_menu").css("display", "block")) {
			$(".top-menu").hide( "drop", "slow" );
			$(".container").css("max-width", "98%");
			$(".container").css("margin-left", "1%");
			$(".show_menu").show();
		} 
	});
	$( "#show_menu" ).click(function() {
			$(".top-menu").show( "drop", "slow" );
			$(".container").css("max-width", "88%");
			$(".container").css("margin-left", "307px");
			$(".show_menu").hide();
	});
	
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
	input = $('<tr><td><input type="text" name="login-add" value="" class="form-control"></td>	<td><input type="passwrod" name="passwrod-add" value="" class="form-control"></td> <td><input type="text" name="role-add" value="" class="form-control"></td><td><input type="text" name="groups-add" value="" class="form-control"></td></tr>');
	$( "#add-user" ).click( function(){
		$( "#users-table" ).append(input);
	});
} );

function removeUser(id) {
	document.getElementById(id).parentNode.removeChild(document.getElementById(id));
    return false;
}