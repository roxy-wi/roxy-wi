function showRuntime() {
	if($('#save').prop('checked')) {
		saveCheck = "on";
	} else {
		saveCheck = "";
	}
	$.ajax({
		url: "/runtimeapi/action/" + $("#serv").val(),
		data: {
			servaction: $('#servaction').val(),
			servbackend: $("#servbackend").val(),
			save: saveCheck,
		},
		type: "POST",
		success: function (data) {
			$("#ajaxruntime").html(data);
		},
		error: function (xhr) {
			RoxywiUI.error(xhr.responseJSON || xhr.responseText);
		}
	} );
}
$( function() {
	$('#runtimeapiform').submit(function () {
		showRuntime();
		return false;
	});
	$('#runtimeapilist').submit(function () {
		getList();
		return false;
	});
	$("#list_serv_select").on('selectmenuchange', function () {
		$.ajax({
			url: "/runtimeapi/list/" + $('#list_serv_select').val(),
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					$('#list_select').find('option').remove();
					for (let value of data ) {
						try {
							value = value.replace(/\'/g, '');
							value = value.replace('(', '');
							value = value.replace(')', '');
							value = value.replace('[', '');
							value = value.replace(']', '');
							id = value.split(' ')[0];
							full_text_option = value.split(' ')[1]
							text_option = full_text_option.split('/').slice(-2)[0];
							text_option = text_option + '/' + full_text_option.split('/').slice(-1)[0];
						} catch (err) {
							text_option = value;
						}
						$('#list_select').append($("<option title=\"Show list " + text_option + "\"></option>")
							.attr("value", id)
							.text(text_option));
					}
					$('#list_select').selectmenu("refresh");
				}
			}
		});
	});
});
function getList() {
	let color = $('#list_select  option:selected').text().split('/')[0];
	let list_name = $('#list_select  option:selected').text().split('/')[1];
	$.ajax({
		url: "/runtimeapi/list/" + $('#list_serv_select').val() + "/" + $('#list_select').val() + "/" + color + "/" + list_name,
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$("#ajaxlist").html(data);
				$("input[type=submit], button").button();
				$.getScript(overview);
				$.getScript(awesome);
			}
		}
	});
}
function deleteListIp(id, list_id, ip_id, ip) {
	toastr.clear();
	$(id).parent().parent().css("background-color", "#f2dede !important");
	$.ajax({
		url: "/runtimeapi/list/delete",
		data: {
			serv: $('#list_serv_select').val(),
			list_id_for_delete: list_id,
			list_ip_id_for_delete: ip_id,
			list_ip_for_delete: ip,
			list_name: $('#list_add_ip').data("list-name"),
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$(id).parent().parent().remove();
				toastr.info('Do not forget upload updated list to the properly server. Restart does not need');
				getList();
			}
		}
	});
}
function addNewIp() {
	toastr.clear();
	let valid = true;
	allFields = $([]).add($('#list_add_ip_new_ip'));
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#list_add_ip_new_ip'), "IP", 1);
	let ip = $('#list_add_ip_new_ip').val();
	if (valid) {
		$.ajax({
			url: "/runtimeapi/list/add",
			data: {
				serv: $('#list_serv_select').val(),
				list_ip_for_add: ip,
				list_id_for_add: $('#list_add_ip').data("list-id"),
				list_name: $('#list_add_ip').data("list-name"),
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error: ') != '-1') {
					toastr.error(data);
				} else {
					getList();
					$("#list_add_ip_form").dialog("destroy");
					toastr.success('IP ' + ip + ' has been added');
					toastr.info('Do not forget upload updated list to the properly server. Restart does not need');
				}
			}
		});
	}
}
