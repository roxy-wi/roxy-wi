var cur_url = window.location.href.split('/').pop();
// cur_url = cur_url.split('/');
let superAdmin_pass = translate_div.attr('data-superAdmin_pass');
$( function() {
	$('#add-user-button').click(function () {
		addUserDialog.dialog('open');
	});
	let user_tabel_title = $("#user-add-table-overview").attr('title');
	let addUserDialog = $("#user-add-table").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: user_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: [{
			text: add_word,
			click: function () {
				addUser(this);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	$("#ajax-users input").change(function () {
		let id = $(this).attr('id').split('-');
		if ($('#role-'+id + ' option:selected' ).val() === 'Select a role') {
			toastr.warning(superAdmin_pass);
			return false;
		} else {
			updateUser(id[1])
		}
	});
	$("#ajax-users select").on('selectmenuchange', function () {
		let id = $(this).attr('id').split('-');
		if ($('#role-'+id + ' option:selected' ).val() === 'Select a role') {
			toastr.warning(superAdmin_pass);
			return false;
		} else {
			updateUser(id[1])
		}
	});
	$('#search_ldap_user').click(function () {
		toastr.clear();
		let username_div = $('#new-username')
		let valid = true;
		let allFields = $([]).add(username_div);
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength(username_div, "user name", 1);
		let user = username_div.val()
		if (valid) {
			$.ajax({
				url: "/user/ldap/" + user,
				contentType: "application/json; charset=utf-8",
				success: function (data) {
					if (data.status === 'failed') {
						toastr.error(data.error);
						$('#new-email').val('');
						username_div.attr('readonly', false);
					} else {
						let json = $.parseJSON(data);
						toastr.clear();
						if (!user.includes('@')) {
							username_div.val(user + '@' + json[1]);
						}
						$('#new-email').val(json[0]);
						$('#new-password').val('aduser');
						$('#new-password').attr('readonly', true);
					}
				}
			});
			clearTips();
		}
	});
} );
function addUser(dialog_id) {
	toastr.clear();
	let valid = true;
	let new_username_div = $('#new-username');
	let password_div = $('#new-password');
	let email_div = $('#new-email');
	let allFields = $([]).add(new_username_div).add(password_div).add(email_div)
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength(new_username_div, "user name", 1);
	valid = valid && checkLength(password_div, "password", 1);
	valid = valid && checkLength(email_div, "Email", 1);
	let enabled = 0;
	if ($('#activeuser').is(':checked')) {
		enabled = '1';
	}
	let user_group = $('#new-group').val();
	if (user_group === undefined || user_group === null) {
		user_group = $('#new-sshgroup').val();
	}
	if (valid) {
		let jsonData = {
			"username": new_username_div.val(),
			"password": password_div.val(),
			"email": email_div.val(),
			"role_id": $('#new-role').val(),
			"enabled": enabled,
			"group_id": user_group,
		}
		$.ajax({
			url: "/user",
			type: "POST",
			data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					let user_id = data.id;
					common_ajax_action_after_success(dialog_id, 'user-' + user_id, 'ajax-users', data.data);
				}
			}
		});
	}
}
function confirmDeleteUser(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word + " " +$('#login-'+id).val() + "?",
      buttons: [{
		  text: delete_word,
		  click: function () {
			  $(this).dialog("close");
			  removeUser(id);
		  }
	  }, {
		  text: cancel_word,
		  click: function () {
			  $(this).dialog("close");
		  }
	  }]
    });
}
function removeUser(id) {
	$("#user-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/user/" + id,
		contentType: "application/json; charset=utf-8",
		type: "DELETE",
		statusCode: {
			204: function (xhr) {
				$("#user-" + id).remove();
			},
			404: function (xhr) {
				$("#user-" + id).remove();
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
function updateUser(id) {
	toastr.remove();
	let enabled = 0;
	if ($('#activeuser-' + id).is(':checked')) {
		enabled = '1';
	}
	let jsonData = {
		"username": $('#login-' + id).val(),
		"email": $('#email-' + id).val(),
		"enabled": enabled,
	}
	$.ajax({
		url: "/user/" + id,
		type: "PUT",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.remove();
				$("#user-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#user-" + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function openChangeUserPasswordDialog(id) {
	changeUserPasswordDialog(id);
}
function openChangeUserServiceDialog(id) {
	changeUserServiceDialog(id);
}
function changeUserPasswordDialog(id) {
	let change_word = translate_div.attr('data-change2');
	let password_word = translate_div.attr('data-password');
	if ($('#role-'+id + ' option:selected' ).val() === 'Select a role') {
		toastr.warning(superAdmin_pass);
		return false;
	}
	$( "#user-change-password-table" ).dialog({
		autoOpen: true,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: change_word + " " + $('#login-' + id).val() + " " + password_word,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: [{
			text: change_word,
			click: function () {
				changeUserPassword(id, $(this));
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				$('#missmatchpass').hide();
			}
		}]
	});
}
function changeUserPassword(id, d) {
	var pass = $('#change-password').val();
	var pass2 = $('#change2-password').val();
	if (pass != pass2) {
		$('#missmatchpass').show();
	} else {
		$('#missmatchpass').hide();
		toastr.clear();
		$.ajax({
			url: "/user/password/" + id,
			data: JSON.stringify({'pass': pass,}),
			type: "POST",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data);
				} else {
					toastr.clear();
					$("#user-" + id).addClass("update", 1000);
					setTimeout(function () {
						$("#user-" + id).removeClass("update");
					}, 2500);
					d.dialog("close");
				}
			}
		});
	}
}
function changeUserServiceDialog(id) {
	let manage_word = translate_div.attr('data-manage');
	let services_word = translate_div.attr('data-services3');
	let save_word = translate_div.attr('data-save');
	let superAdmin_services = translate_div.attr('data-superAdmin_services');
	if ($('#role-' + id + ' option:selected').val() == 'Select a role') {
		toastr.warning(superAdmin_services);
		return false;
	}
	$.ajax({
		url: "/user/services/" + id,
		success: function (data) {
			if (data.indexOf('danger') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$('#change-user-service-form').html(data);
				$("#change-user-service-dialog").dialog({
					resizable: false,
					height: "auto",
					width: 700,
					modal: true,
					title: manage_word + " " + $('#login-' + id).val() + " " + services_word,
					buttons: [{
						text: save_word,
						click: function () {
							$(this).dialog("close");
							changeUserServices(id);
						}
					}, {
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}]
				});
			}
		}
	});
}
function changeUserServices(user_id) {
	let jsonData = {};
	jsonData['services'] = {};
	jsonData['services'][user_id] = {};
	jsonData['username'] = $('#login-'+user_id).val();
	$('#checked_services tbody tr').each(function () {
		let this_id = $(this).attr('id').split('-')[1];
		jsonData['services'][user_id][this_id] = {}
	});
	$.ajax( {
		url: "/user/services/" + user_id,
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "POST",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				$("#user-" + user_id).addClass("update", 1000);
				setTimeout(function () {
					$("#user-" + user_id).removeClass("update");
				}, 2500);
			}
		}
	} );
}
function addServiceToUser(service_id) {
	let service_name = $('#add_service-'+service_id).attr('data-service_name');
	let length_tr = $('#checked_services tbody tr').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<tr class="'+tr_class+'" id="remove_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="removeServiceFromUser('+service_id+')" title="'+delete_word+' '+service_word+'">-</span></td></tr>';
	$('#add_service-'+service_id).remove();
	$("#checked_services tbody").append(html_tag);
}
function removeServiceFromUser(service_id) {
	let service_name = $('#remove_service-'+service_id).attr('data-service_name');
	let length_tr = $('#all_services tbody tr').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<tr class="'+tr_class+'" id="add_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="addServiceToUser('+service_id+')" title="'+add_word+' '+service_word+'">+</span></td></tr>';
	$('#remove_service-'+service_id).remove();
	$("#all_services tbody").append(html_tag);
}
function confirmChangeGroupsAndRoles(user_id) {
	let user_groups_word = translate_div.attr('data-user_groups');
	let username = $('#login-' + user_id).val();
	let groups = getAllGroups();
	$.ajax({
		url: "/user/" + user_id + "/groups",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			$("#checked_groups tbody").html('');
			$("#all_groups tbody").html('');
			for (let group of groups) {
				removeGroupFromUser(group.group_id, group.name, group.description)
			}
			for (let group of data) {
				addGroupToUser(group.user_group_id, group.user_role_id);
			}
			$("#groups-roles").dialog({
				resizable: false,
				height: "auto",
				width: 700,
				modal: true,
				title: user_groups_word + ' ' + username,
				buttons: [{
					text: save_word,
					click: function () {
						saveGroupsAndRoles(user_id);
						$(this).dialog("close");
					}
				}, {
					text: cancel_word,
					click: function () {
						$(this).dialog("close");
					}
				}]
			});
		}
	});
}
function addGroupToUser(group_id, user_role_id=0) {
	let group_name = $('#add_group-' + group_id).attr('data-group_name');
	let group2_word = translate_div.attr('data-group2');
	let length_tr = $('#all_groups tbody tr').length;
	const roles = {1: 'superAdmin', 2: 'admin', 3: 'user', 4: 'guest'};
	let options_roles = '';
	for (const [role_id, role_name] of Object.entries(roles)) {
		console.log(user_role_id)
		if (user_role_id === Number(role_id)) {
			options_roles += '<option value="' + role_id + '" selected>' + role_name + '</option>';
		} else {
			options_roles += '<option value="' + role_id + '">' + role_name + '</option>';
		}
	}
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<tr class="' + tr_class + '" id="remove_group-' + group_id + '" data-group_name="' + group_name + '">\n' +
		'        <td class="padding20" style="width: 50%;">' + group_name + '</td>\n' +
		'        <td style="width: 50%;">\n' +
		'            <select id="add_role-' + group_id + '">' + options_roles + '</select></td>\n' +
		'        <td><span class="remove_user_group" onclick="removeGroupFromUser(' + group_id + ')" title="' + delete_word + ' ' + group2_word + '">-</span></td></tr>'
	$('#add_group-' + group_id).remove();
	$("#checked_groups tbody").append(html_tag);
}
function removeGroupFromUser(group_id, name=false, desc=false) {
	let group_name = $('#remove_group-'+group_id).attr('data-group_name');
	let description = '';
	if (name) {
		group_name = name;
		description = desc;
	}

	let group2_word = translate_div.attr('data-group2');
	let length_tr = $('#all_groups tbody tr').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<tr class="'+tr_class+'" id="add_group-'+group_id+'" data-group_name='+group_name+'>\n' +
		'    <td class="padding20" style="width: 100%">'+group_name+'</td>\n' +
		'    <td><span class="add_user_group" title="'+add_word+' '+group2_word+'" title="'+description+'" onclick="addGroupToUser('+group_id+')">+</span></td></tr>'
	$('#remove_group-'+group_id).remove();
	$("#all_groups tbody").append(html_tag);
}
function saveGroupsAndRoles(user_id) {
	let length_tr = $('#checked_groups tbody tr').length;
	let jsonData = {};
	jsonData[user_id] = {};
	$('#checked_groups tbody tr').each(function () {
		let this_id = $(this).attr('id').split('-')[1];
		let role_id = $('#add_role-' + this_id).val();
		jsonData[user_id][this_id] = {'role_id': role_id};
	});
	for (const [key, value] of Object.entries(jsonData)) {
		if (Object.keys(value).length === 0) {
			toastr.error('error: User must have at least one group');
			return false;
		}
	}
	$.ajax({
		url: "/user/groups/save",
		data: {
			changeUserGroupsUser: $('#login-' + user_id).val(),
			jsonDatas: JSON.stringify(jsonData)
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.warning(data);
			} else {
				$("#user-" + user_id).addClass("update", 1000);
				setTimeout(function () {
					$("#user-" + user_id).removeClass("update");
				}, 2500);
			}
		}
	});
}
