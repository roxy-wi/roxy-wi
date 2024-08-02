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
	let name = $('#new-group-add').val();
    let desc = $('#new-desc').val();
	if (valid) {
		let jsonData = {
			'name': name,
			'desc': desc
		}
		$.ajax({
			url: "/server/group",
			type: 'POST',
			data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data);
				} else {
					let id = data.id;
					$('select:regex(id, group)').append('<option value=' + id + '>' + $('#new-group-add').val() + '</option>').selectmenu("refresh");
					let new_group = elem("tr", {"id":"group-"+id,"class":"newgroup"}, [
                        elem("td", {"class":"padding10","style":"width: 0"}, id),
                        elem("td", {"class":"padding10 first-collumn"}, [
                            elem("input", {"type":"text","name":"name-"+id,"value": name,"id":"name-"+id,"class":"form-control","autocomplete":"off"})
                        ]),
                        elem("td", null, [
                            elem("input", {"type":"text","name":"descript-"+id,"value":desc,"id":"descript-"+id,"size":"60","class":"form-control","autocomplete":"off"})
                        ]),
                        elem("td", null, [
                            elem("a", {"class":"delete","onclick":"confirmDeleteGroup("+id+")","title":"Delete group "+name,"style":"cursor: pointer;"})
                        ])
                    ])
                    common_ajax_action_after_success(dialog_id, 'newgroup', 'ajax-group', new_group);
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
	}
	$.ajax({
		url: "/server/group/" + id,
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
        url: "/server/group/" + id,
        type: 'DELETE',
        contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#group-" + id).remove();
                $('select:regex(id, group) option[value=' + id + ']').remove();
                $('select:regex(id, group)').selectmenu("refresh");
			},
			404: function (xhr) {
				$("#group-" + id).remove();
                $('select:regex(id, group) option[value=' + id + ']').remove();
                $('select:regex(id, group)').selectmenu("refresh");
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
function getGroupNameById(group_id) {
	let group_name = ''
	$.ajax({
		url: "/server/group/" + group_id,
		async: false,
        contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				group_name = data.name;
			}
		}
	});
	return group_name;
}
