$( function() {
    $("#nettools_nslookup_record_type").selectmenu({
        width: 175
    });
    $("#nettools_telnet_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        let frm = $('#nettools_telnet_form');
        if ($('#nettools_telnet_server_from option:selected').val() == '------') {
            toastr.warning('Choose a server From');
            return false;
        }
        if ($('#nettools_telnet_server_to').val() == '') {
            toastr.warning('Choose a server To');
            return false;
        }
        if ($('#nettools_telnet_port_to').val() == '') {
            toastr.warning('Enter a port To');
            return false;
        }
        $.ajax({
            url: frm.attr('action'),
            data: frm.serialize(),
            type: frm.attr('method'),
            success: function (data) {
                data = data.replace('\n', "<br>");
                if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1' || data.indexOf('Error(s)') != '-1') {
                    $('#ajax-nettools').html('<div class="ping_pre">' + data + '</div>');
                } else if (data.indexOf('warning: ') != '-1') {
                    toastr.clear();
                    toastr.warning(data)
                } else {
                    toastr.clear();
                    if (data.indexOf('') != '-1') {
                        $('#ajax-nettools').html('<div class="ping_pre"><b>Connection has been successful</b></div>');
                    } else {
                        $('#ajax-nettools').html('<div class="ping_pre"><b>Connection has been successful</b>:<br /><br />' + data + '</div>');
                    }
                }
            }
        });
        event.preventDefault();
    });
    $("#nettools_nslookup_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        let frm = $('#nettools_nslookup_form');
        if ($('#nettools_nslookup_server_from option:selected').val() == '------') {
            toastr.warning('Choose a server From');
            return false;
        }
        if ($('#nettools_nslookup_name').val() == '') {
            toastr.warning('Enter a DNS name');
            return false;
        }
        $.ajax({
            url: frm.attr('action'),
            data: frm.serialize(),
            type: frm.attr('method'),
            success: function (data) {
                data = data.replace('\n', "<br>");
                if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1' || data.indexOf('Error(s)') != '-1') {
                    toastr.clear();
                    toastr.error(data);
                } else if (data.indexOf('warning: ') != '-1') {
                    toastr.clear();
                    toastr.warning(data)
                } else {
                    toastr.clear();
                    $('#ajax-nettools').html('<div class="ping_pre">' + data + '</div>');
                }
            }
        });
        event.preventDefault();
    });
    $("#nettools_icmp_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        let frm = $('#nettools_icmp_form');
        if ($('#nettools_icmp_server_from option:selected').val() == '------') {
            toastr.warning('Choose a server From');
            return false;
        }
        if ($('#nettools_icmp_server_to').val() == '') {
            toastr.warning('Enter a server To');
            return false;
        }
        $.ajax({
            url: frm.attr('action'),
            data: frm.serialize() + "&nettools_action=" + $(this).val(),
            type: frm.attr('method'),
            xhrFields: {
                onprogress: function (e) {
                    console.log(e.currentTarget.responseText);
                    $('#ajax-nettools').html(e.currentTarget.responseText);
                }
            },
            dataType: 'text',
            success: function (data) {
                data = data.replace('\n', "<br>");
                if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1' || data.indexOf('Error(s)') != '-1') {
                    toastr.clear();
                    toastr.error(data);
                } else if (data.indexOf('warning: ') != '-1') {
                    toastr.clear();
                    toastr.warning(data)
                } else {
                    toastr.clear();
                }
            }
        });
        event.preventDefault();
    });
    $("#nettools_portscanner_form").on("click", ":submit", function (e) {
        let port_server = $('#nettools_portscanner_server').val();
        $('#ajax-nettools').html('');
        if (port_server == '') {
            toastr.warning('Enter an address');
            return false;
        }
        $.ajax({
            url: "/app/portscanner/scan",
            data: JSON.stringify({'ip': port_server}),
            type: "POST",
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.error(data.error);
                } else {
                    toastr.clear();
                    $("#show_scans_ports_body").html(data.data);
                    $("#show_scans_ports").dialog({
                        resizable: false,
                        height: "auto",
                        width: 360,
                        modal: true,
                        title: "Opened ports",
                        buttons: [{
                            text: close_word,
                            click: function () {
                                $(this).dialog("close");
                                $("#show_scans_ports_body").html('');
                            }
                        }]
                    });
                }
            }
        });
        event.preventDefault();
    });
    $("#nettools_whois_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        let frm = $('#nettools_whois_form');
        if ($('#nettools_whois_name').val() == '') {
            toastr.warning('Enter a Domain name');
            return false;
        }
        $.ajax({
            url: frm.attr('action'),
            data: frm.serialize() + "&nettools_action=" + $(this).val(),
            type: frm.attr('method'),
            dataType: 'text',
            success: function (data) {
                data = data.replaceAll('"', '');
                if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1' || data.indexOf('Error(s)') != '-1') {
                    toastr.clear();
                    toastr.error(data);
                } else if (data.indexOf('warning: ') != '-1') {
                    toastr.clear();
                    toastr.warning(data)
                } else {
                    toastr.clear();
                    console.log(data)
                    $('#ajax-nettools').html('<div class="ping_pre">' + data + '</div>');
                }
            }
        });
        event.preventDefault();
    });
});
