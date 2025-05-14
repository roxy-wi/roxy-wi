$( function() {
    $('#add-saved-server-button').click(function () {
        if ($('#saved-server-add-table').css('display', 'none')) {
            $('#saved-server-add-table').show("blind", "fast");
        }
    });
    $('#add-saved-server-new').click(function () {
        $.ajax({
            url: "/add/server",
            data: JSON.stringify({
                server: $('#new-saved-servers').val(),
                description: $('#new-saved-servers-description').val()
            }),
            type: "POST",
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.error(data);
                } else {
                    $("#servers_table").append(data.data);
                    setTimeout(function () {
                        $(".newsavedserver").removeClass("update");
                    }, 2500);
                    $.getScript(overview);
                }
            }
        });
    });
    $("#servers_table input").change(function () {
		let id = $(this).attr('id').split('-');
		updateSavedServer(id[2])
	});
	$('[name=servers]').autocomplete({
		source: "/add/server/get/" + $('#group_id').val(),
		autoFocus: true,
		minLength: 1,
		select: function (event, ui) {
			$(this).append(ui.item.value + " ");
			$(this).next().focus();
		}
	})
		.autocomplete("instance")._renderItem = function (ul, item) {
		return $("<li>")
			.append("<div>" + item.value + "<br>" + item.desc + "</div>")
			.appendTo(ul);
	};
});
function updateSavedServer(id) {
	toastr.clear();
	$.ajax( {
		url: "/add/server/" + id,
		type: "PUT",
		data: JSON.stringify({"server": $('#servers-ip-'+id).val(), description: $('#servers-desc-'+id).val(),}),
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				$("#servers-saved-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#servers-saved-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function confirmDeleteSavedServer(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#servers-ip-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeSavedServer(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function removeSavedServer(id) {
	$("#servers-saved-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/add/server/" + id,
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#servers-saved-" + id).remove();
			},
			404: function (xhr) {
				$("#servers-saved-" + id).remove();
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === "failed") {
					toastr.error(data);
				}
			}
		}
	});
}
