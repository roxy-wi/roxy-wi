let groupDeploymentPolicyDialog;
let deploymentPolicyTranslations = {};

$( function() {
	try {
		deploymentPolicyTranslations = JSON.parse($('#deployment-policy-translations').text() || '{}');
	} catch (_error) {
		deploymentPolicyTranslations = {};
	}
	$('#add-group-button').click(function () {
		addGroupDialog.dialog('open');
	});
	$('#ajax-group').on('click', '.group-deployment-policy-button', function () {
		loadGroupDeploymentPolicy($(this).data('group-id'), $(this).data('group-name'));
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
	groupDeploymentPolicyDialog = $('#group-deployment-policy-dialog').dialog({
		autoOpen: false,
		resizable: false,
		height: 'auto',
		width: 620,
		modal: true,
		dialogClass: 'deployment-policy-modal',
		buttons: [{
			text: deploymentPolicyTranslations.save || 'Save policy',
			click: saveGroupDeploymentPolicy
		}, {
			text: deploymentPolicyTranslations.cancel || 'Cancel',
			click: function () { $(this).dialog('close'); }
		}]
	});
	$('#group-deployment-policy-form select').selectmenu({width: '100%'});
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
					let actionsLabel = $('#ajax-group th.admin-actions-cell').text().trim() || 'Actions';
					$('select:regex(id, group)').append('<option value=' + id + '>' + $('#new-group-add').val() + '</option>').selectmenu("refresh");
					let new_group = elem("tr", {"id":"group-"+id,"class":"newgroup"}, [
                        elem("td", {"class":"padding10","style":"width: 0"}, id),
                        elem("td", {"class":"padding10 first-collumn"}, [
                            elem("input", {"type":"text","name":"name-"+id,"value": name,"id":"name-"+id,"class":"form-control","autocomplete":"off"})
                        ]),
                        elem("td", null, [
                            elem("input", {"type":"text","name":"descript-"+id,"value":desc,"id":"descript-"+id,"size":"60","class":"form-control","autocomplete":"off"})
                        ]),
						elem("td", {"class":"admin-actions-cell"}, [
							elem("div", {"class":"admin-actions"}, [
								elem("button", {
									"type":"button", "class":"rw-icon-button admin-actions-toggle",
									"aria-haspopup":"menu", "aria-expanded":"false",
									"title":actionsLabel, "aria-label":actionsLabel
								}, [elem("span", {"class":"fas fa-ellipsis-v", "aria-hidden":"true"})]),
								elem("div", {"class":"admin-actions-menu", "role":"menu", "hidden":"hidden"}, [
									elem("button", {
										"type":"button", "class":"admin-action-item group-deployment-policy-button",
										"data-group-id":id, "data-group-name":name
									}, [
										elem("span", {"class":"fas fa-shield-alt", "aria-hidden":"true"}),
										deploymentPolicyTranslations.configure || "Configure deployment policy"
									]),
									elem("button", {
										"type":"button", "class":"admin-action-item admin-action-item-danger",
										"onclick":"confirmDeleteGroup("+id+")"
									}, [
										elem("span", {"class":"fas fa-trash-alt", "aria-hidden":"true"}),
										delete_word
									])
								])
							])
						])
                    ])
                    common_ajax_action_after_success(dialog_id, 'newgroup', 'ajax-group', new_group);
				}
			}
		});
	}
}

function deploymentPolicyError(xhr, fallback) {
	let response = xhr && xhr.responseJSON;
	return response && response.error ? response.error : fallback;
}

function loadGroupDeploymentPolicy(groupId, groupName) {
	$.ajax({
		url: '/server/group/' + groupId + '/deployment-policy',
		type: 'GET',
		dataType: 'json',
		success: function (response) {
			$('#deployment-policy-group-id').val(groupId);
			$('#deployment-policy-group-name').text(groupName);
			Object.keys(response.data).forEach(function (service) {
				let select = $('#deployment-policy-' + service);
				select.val(response.data[service]);
				if (select.selectmenu('instance')) {
					select.selectmenu('refresh');
				}
			});
			groupDeploymentPolicyDialog.dialog('open');
		},
		error: function (xhr) {
			toastr.error(deploymentPolicyError(xhr, deploymentPolicyTranslations.load_error || 'Cannot load deployment policy'));
		}
	});
}

function saveGroupDeploymentPolicy() {
	let groupId = $('#deployment-policy-group-id').val();
	let policy = {};
	$('#group-deployment-policy-form select').each(function () {
		policy[this.name] = $(this).val();
	});
	$.ajax({
		url: '/server/group/' + groupId + '/deployment-policy',
		type: 'PUT',
		data: JSON.stringify(policy),
		contentType: 'application/json; charset=utf-8',
		dataType: 'json',
		success: function () {
			groupDeploymentPolicyDialog.dialog('close');
			toastr.success(deploymentPolicyTranslations.saved || 'Deployment policy saved');
		},
		error: function (xhr) {
			toastr.error(deploymentPolicyError(xhr, deploymentPolicyTranslations.save_error || 'Cannot save deployment policy'));
		}
	});
}
function updateGroup(id) {
	toastr.clear();
	let jsonData = {
		"name": $('#name-' + id).val(),
		"description": $('#descript-' + id).val(),
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
