$( function() {
	$('#add-group-button').click(function () {
		addGroupDialog.dialog('open');
	});
	let group_tabel_title = $("#group-add-table-overview").attr('title');
	let addGroupDialog = $("#group-add-table").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: group_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Add": function () {
				addGroup(this);
			},
			Cancel: function () {
				$(this).dialog("close");
				clearTips();
			}
		}
	});
	$("#ajax-group input").change(function () {
		let id = $(this).attr('id').split('-');
		updateGroup(id[1])
	});
});
function addGroup(dialog_id) {
	toastr.clear();
	let valid = true;
	let allFields = $([]).add($('#new-group-add'));
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#new-group-add'), "new group name", 1);
	if (valid) {
		let jsonData = {
			'name': $('#new-group-add').val(),
			'desc': $('#new-desc').val()
		}
		$.ajax({
			url: "/app/server/group",
			type: 'POST',
			data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data);
				} else {
					let id = data.id;
					$('select:regex(id, group)').append('<option value=' + id + '>' + $('#new-group-add').val() + '</option>').selectmenu("refresh");
					common_ajax_action_after_success(dialog_id, 'newgroup', 'ajax-group', data.data);
				}
			}
		});
	}
}
function updateGroup(id) {
	toastr.clear();
	let jsonData = {
		"name": $('#name-' + id).val(),
		"desc": $('#descript-' + id).val(),
		"group_id": id
	}
	$.ajax({
		url: "/app/server/group",
		type: "PUT",
		data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data);
			} else {
				toastr.clear();
				$("#group-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#group-" + id).removeClass("update");
				}, 2500);
				$('select:regex(id, group) option[value=' + id + ']').remove();
				$('select:regex(id, group)').append('<option value=' + id + '>' + $('#name-' + id).val() + '</option>').selectmenu("refresh");
			}
		}
	});
}
function confirmDeleteGroup(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word+ " " +$('#name-'+id).val() + "?",
      buttons:  [{
		  text: delete_word,
		  click: function() {
			  $(this).dialog("close");
			  removeGroup(id);
		  }
        }, {
		  text: cancel_word,
		  click: function () {
			  $(this).dialog("close");
		  }
	  }]
    });
}
function removeGroup(id) {
    $("#group-" + id).css("background-color", "#f2dede");
    $.ajax({
        url: "/app/server/group",
        type: 'DELETE',
        data: JSON.stringify({'group_id': id}),
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data.error);
            } else {
                $("#group-" + id).remove();
                $('select:regex(id, group) option[value=' + id + ']').remove();
                $('select:regex(id, group)').selectmenu("refresh");
            }
        }
    });
}
function getGroupNameById(group_id) {
	let group_name = ''
	$.ajax({
		url: "/app/user/group/name/" + group_id,
		async: false,
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				group_name = data;
			}
		}
	});
	return group_name;
}
