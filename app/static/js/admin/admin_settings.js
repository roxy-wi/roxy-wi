$( function() {
   $('#nginx-section-head').click(function () {
		hideAndShowSettings('nginx');
	});
	$('#main-section-head').click(function () {
		hideAndShowSettings('main');
	});
	$('#monitoring-section-head').click(function () {
		hideAndShowSettings('monitoring');
	});
	$('#haproxy-section-head').click(function () {
		hideAndShowSettings('haproxy');
	});
	$('#ldap-section-head').click(function () {
		hideAndShowSettings('ldap');
	});
	$('#logs-section-head').click(function () {
		hideAndShowSettings('logs');
	});
	$('#rabbitmq-section-head').click(function () {
		hideAndShowSettings('rabbitmq');
	});
	$('#apache-section-head').click(function () {
		hideAndShowSettings('apache');
	});
	$('#caddy-section-head').click(function () {
		hideAndShowSettings('caddy');
	});
	$('#keepalived-section-head').click(function () {
		hideAndShowSettings('keepalived');
	});
	$('#mail-section-head').click(function () {
		hideAndShowSettings('mail');
	});
	$('#smon-section-head').click(function () {
		hideAndShowSettings('smon');
	});
	$( "#settings select" ).on('select2:select',function() {
		var id = $(this).attr('id');
		var val = $(this).val();
		updateSettings(id, val);
		let section = $(this).parent().parent().attr('class').split(' ')[1].split('-')[0];
		updateSettings(id, section, val);
	});
	$( "#settings input" ).change(function() {
		var id = $(this).attr('id');
		var val = $(this).val();
		if($('#'+id).is(':checkbox')) {
			if ($('#'+id).is(':checked')){
				val = '1';
			} else {
				val = '0';
			}
		}
		let section = $(this).parent().parent().attr('class').split(' ')[1].split('-')[0];
		updateSettings(id, section, val);
	});
});
function hideAndShowSettings(section) {
	var ElemId = $('#' + section + '-section-h3');
	if(ElemId.attr('class') == 'plus-after') {
		$('.' + section + '-section').show();
		ElemId.removeClass('plus-after');
		ElemId.addClass('minus-after');
		$.getScript(awesome);
	} else {
		$('.' + section + '-section').hide();
		ElemId.removeClass('minus-after');
		ElemId.addClass('plus-after');
		$.getScript(awesome);
	}
}
function updateSettings(param, section, val) {
	try {
		val = val.replace(/\//g, "92");
	} catch (e) {
		val = val;
	}
	toastr.clear();
	let json_data = {
		'param': param,
		'value': val
	}
	$.ajax({
		url: "/admin/settings/" + section,
		data: JSON.stringify(json_data),
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#" + param).parent().parent().addClass("update", 1000);
				setTimeout(function () {
					$("#" + param).parent().parent().removeClass("update");
				}, 2500);
			}
		}
	});
}
