$( function() {
	$("input[type=submit], button").not(".config-viewer button").button();
	$("#saveconfig").on("click", ":submit", function (e) {
		let frm = $('#saveconfig');
		myCodeMirror.save();

		let unindexed_array = frm.serializeArray();
		let indexed_array = {};
		$.map(unindexed_array, function (n, i) {
			if (n['value'] != 'undefined') {
				indexed_array[n['name']] = n['value'];
			}
		});
		indexed_array['action'] = $(this).val();
		$.ajax({
			url: frm.attr('action'),
			dataType: 'json',
			data: JSON.stringify(indexed_array),
			type: frm.attr('method'),
			contentType: "application/json; charset=UTF-8",
			success: function (data) {
				toastr.clear();
				data.data = data.data.replace(/\n/g, "<br>");
				returnNiceCheckingConfig(data.data);
				$(window).unbind('beforeunload');
				if (data.status === 'failed') {
					toastr.warning(data.error)
				}
			}
		});
		e.preventDefault();
	});

	$(document).off("click.configVersion", "#save_version :submit").on("click.configVersion", "#save_version :submit", function (e) {
		let frm = $('#save_version');
		let unindexed_array = frm.serializeArray();
		let indexed_array = {};
		$.map(unindexed_array, function (n, i) {
			if (n['value'] != 'undefined') {
				indexed_array[n['name']] = n['value'];
			}
		});
		indexed_array['action'] = $(this).val();
		$.ajax({
			url: frm.attr('action'),
			dataType: 'json',
			data: JSON.stringify(indexed_array),
			type: frm.attr('method'),
			contentType: "application/json; charset=UTF-8",
			success: function (data) {
				toastr.clear();
				data.data = data.data.replace(/\n/g, "<br>");
				returnNiceCheckingConfig(data.data);
				if (data.status === 'failed') {
					toastr.warning(data.error)
				}
			}
		});
		e.preventDefault();
	});
	$(document).off("click.configDeleteVersions", "#delete_versions_form :submit").on("click.configDeleteVersions", "#delete_versions_form :submit", function (e) {
		let frm = $('#delete_versions_form');
		let unindexed_array = frm.serializeArray();
		let indexed_array = {};
		indexed_array['versions'] = [];
		$.map(unindexed_array, function (n, i) {
			if (n['value'] != 'undefined') {
				if (n['name'] === 'versions') {
					indexed_array['versions'].push(n['value']);
				} else {
					indexed_array[n['name']] = n['value'];
				}
			}
		});
		indexed_array['action'] = $(this).val();
		$.ajax({
			url: frm.attr('action'),
			dataType: 'json',
			data: JSON.stringify(indexed_array),
			type: frm.attr('method'),
			contentType: "application/json; charset=UTF-8",
			statusCode: {
				204: function (xhr) {
					toastr.success('The versions of configs have been deleted');
					showListOfVersion(1);
				},
				404: function (xhr) {
					toastr.success('The versions of configs have been deleted');
					showListOfVersion(1);
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
		e.preventDefault();
	});
})
function compareConfig(div_id, diff) {
	const container = document.getElementById(div_id);
	container.innerHTML = "";
	const diffUi = new Diff2HtmlUI(container, diff, {
		inputFormat: 'diff',
		matching: 'lines',
		fileListToggle: false,
		drawFileList: true,
		fileContentToggle: false,
		outputFormat: 'line-by-line', // или 'line-by-line'
	});
	diffUi.draw();
	diffUi.highlightCode();
}
function showCompare() {
	$.ajax({
		url: "/config/compare/" + $("#service").val() + "/" + $("#serv").val() + "/show",
		data: JSON.stringify({
			left: $('#left').val(),
			right: $("#right").val(),
		}),
		contentType: "application/json; charset=utf-8",
		type: "POST",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				toastr.clear();
				compareConfig('ajax', data.compare);
			}
		}
	});
}
function showCompareConfigs() {
	clearAllAjaxFields();
	$('#ajax-config_file_name').empty();
	$.ajax({
		url: "/config/compare/" + $("#service").val() + "/" + $("#serv").val() + "/files",
		type: "GET",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-compare").html(data);
				$("input[type=submit], button").button();
				$("select").selectmenu();
				window.history.pushState("Show compare config", "Show compare config", '/config/compare/' + $("#service").val() + '/' + $("#serv").val());
			}
		}
	});
}
