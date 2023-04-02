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
	$('#keepalived-section-head').click(function () {
		hideAndShowSettings('keepalived');
	});
	$('#mail-section-head').click(function () {
		hideAndShowSettings('mail');
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
