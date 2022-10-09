$( function() {
    $(".redirectUpstream").on("click", function () {
        resetProxySettings();
        $("#tabs").tabs("option", "active", 1);
        $("#serv").selectmenu("open");
    });
    $( "#serv" ).on('selectmenuchange',function() {
		$('#name').focus();
	});
    var add_server_var = '<br /><input name="servers" title="Backend IP" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control second-server" style="margin: 2px 0 4px 0;">: ' +
		'<input name="server_port" required title="Backend port" size=3 placeholder="yyy" class="form-control second-server add_server_number" type="number"> ' +
		'max_fails check: <input name="max_fails" required title="By default, the number of unsuccessful attempts is set to 1" size=5 value="1" class="form-control add_server_number" type="number">' +
		' fail_timeout: <input name="fail_timeout" required title="By default, the number of unsuccessful attempts is set to 1" size=5 value="1" class="form-control add_server_number" type="number">s'
	$('[name=add-server-input]').click(function() {
		$("[name=add_servers]").append(add_server_var);
		changePortCheckFromServerPort();
	});
    $('.advance-show-button').click(function() {
		$('.advance').fadeIn();
		$('.advance-show-button').css('display', 'none');
		$('.advance-hide-button').css('display', 'block');
		return false;
	});
	$('.advance-hide-button').click(function() {
		$('.advance').fadeOut();
		$('.advance-show-button').css('display', 'block');
		$('.advance-hide-button').css('display', 'none');
		return false;
	});
});
function resetProxySettings() {
    $('[name=upstream]').val('');
    $('input:checkbox').prop("checked", false);
    $('[name=check-servers]').prop("checked", true);
    $('input:checkbox').checkboxradio("refresh");
    $('.advance-show').fadeIn();
    $('.advance').fadeOut();
    $('[name=mode').val('http');
    $('select').selectmenu('refresh');
    $("#path-cert-listen").attr('required', false);
    $("#path-cert-frontend").attr('required', false);
    // replace_text("#optionsInput", ssl_offloading_var);
    // replace_text("#optionsInput1", ssl_offloading_var);
}
function checkIsServerFiled(select_id, message = 'Select a server first') {
	if ($(select_id).val() == null || $(select_id).val() == '') {
		toastr.warning(message);
		return false;
	}
	return true;
}
function generateConfig(form_name) {
	var frm = $('#'+form_name);
	if (form_name == 'add-upstream') {
		serv = '#serv'
		name_id = '#name'
	}
	if(!checkIsServerFiled(serv)) return false;
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	var input = $("<input>")
		.attr("name", "generateconfig").val("1").attr("type", "hidden").attr("id", "generateconfig");
	$('#'+form_name +' input[name=acl_then_value]').each(function(){
		if (!$(this).val()){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=ip]').each(function(){
		if (!$(this).val()){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if (!$(this).val()){
			$(this).val('IsEmptY')
		}
	});
	frm.append(input);
	$.ajax({
		url: frm.attr('action'),
		data: frm.serialize(),
		type: frm.attr('method'),
		success: function (data) {
			if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1') {
				toastr.clear();
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$("#dialog-confirm-cert").dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Generated config",
					buttons: {
						Ok: function () {
							$(this).dialog("close");
						}
					}
				});
			}
		}
	});
	$("#generateconfig").remove();
    $('#'+form_name +' input[name=ip]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
}
function addProxy(form_name) {
	var frm = $('#'+form_name);
	if (form_name == 'add-upstream') {
		serv = '#serv'
		name_id = '#name'
	}
	if(!checkIsServerFiled(serv)) return false;
	if(!checkIsServerFiled(name_id, 'The name cannot be empty')) return false;
	$('#'+form_name +' input[name=ip]').each(function(){
		if ($(this).val().length === 0){
			$(this).val('IsEmptY')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if ($(this).val().length === 0){
			$(this).val('IsEmptY')
		}
	});
	$.ajax({
		url: frm.attr('action'),
		data: frm.serialize(),
		type: frm.attr('method'),
		success: function( data ) {
			data = data.replace(/\n/g, "<br>");
			if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1') {
				returnNiceCheckingConfig(data);
			} else if (data == '') {
				toastr.clear();
				toastr.error('error: Proxy cannot be empty');
			} else {
				toastr.clear();
				returnNiceCheckingConfig(data);
				toastr.info('Section has been added. Do not forget to restart the server');
				resetProxySettings();
			}
		}
	});
	$('#'+form_name +' input[name=ip]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
	$('#'+form_name +' input[name=port]').each(function(){
		if ($(this).val() == 'IsEmptY'){
			$(this).val('')
		}
	});
}