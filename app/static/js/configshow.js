$( function() {
	$("input[type=submit], button").button();
	$(".configShow").accordion({
		collapsible: true,
		heightStyle: "content",
		icons: {"header": "ui-icon-plus", "activeHeader": "ui-icon-minus"}
	});
	$('#raw').click(function () {
		$(".configShow").accordion("destroy");
		$('#raw').css('display', 'none');
		$('.numRow').css('display', 'none');
		$('#according').css('display', 'inline-block');
		$('.accordion-expand-all').css('display', 'none');
	});
	$('#according').click(function () {
		$(".configShow").accordion({
			collapsible: true,
			heightStyle: "content",
			icons: {"header": "ui-icon-plus", "activeHeader": "ui-icon-minus"}
		});
		$('#raw').css('display', 'inline-block');
		$('.numRow').css('display', 'inline-block');
		$('#according').css('display', 'none');
		$('.accordion-expand-all').css('display', 'inline-block');
	});
	let headers = $('.configShow .accordion-header');
	let contentAreas = $('.configShow .ui-accordion-content ').hide()
		.first().show().end();
	let expandLink = $('.accordion-expand-all');
	headers.click(function () {
		// close all panels
		contentAreas.slideUp();
		// open the appropriate panel
		$(this).next().slideDown();
		// reset Expand all button
		expandLink.text('Expand all')
			.data('isAllOpen', false);
		// stop page scroll
		return false;
	});
	// hook up the expand/collapse all
	expandLink.click(function () {
		let isAllOpen = !$(this).data('isAllOpen');
		console.log({isAllOpen: isAllOpen, contentAreas: contentAreas})
		contentAreas[isAllOpen ? 'slideDown' : 'slideUp']();

		expandLink.text(isAllOpen ? 'Collapse All' : 'Expand all')
			.data('isAllOpen', isAllOpen);
	});
	$(".accordion-link a").on("click", function (event) {
		window.location.href = $(this).attr("href");
		event.preventDefault();
	});

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

	$("#save_version").on("click", ":submit", function (e) {
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
	$("#delete_versions_form").on("click", ":submit", function (e) {
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
