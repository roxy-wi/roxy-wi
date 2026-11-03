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
});
