var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
function ajaxActionServers(action, id) {
		var bad_ans = 'Bad config, check please';
		$.ajax( {
				url: "options.py",
				data: {
					action: action,
					serv: id
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if( data ==  'Bad config, check please ' ) {
						alert(data);
					} else {
						setTimeout(showOverview, 2000)
					}
				},
				error: function(){
					alert(w.data_error);
				}					
			} );
	}
	
$( function() {
	$('.start').click(function() {
		var id = $(this).attr('id');
		ajaxActionServers("start", id);
	});
	$('.stop').click(function() {
		var id = $(this).attr('id');
		ajaxActionServers("stop", id);
	});
	$('.restart').click(function() {
		var id = $(this).attr('id');
		ajaxActionServers("restart", id);
	});
	$ ( "#show-all-users" ).click( function() {
		if($( "#show-all-users" ).text() == "Show all") {
			$( ".show-users" ).show("fast");
			$( "#show-all-users" ).text("Hide");
			$( "#show-all-users" ).attr("title", "Hide all users"); 
		} else {
			$( ".show-users" ).hide("fast");
			$( "#show-all-users" ).attr("title", "Show all users");
			$( "#show-all-users" ).text("Show all");
		}
	});
});