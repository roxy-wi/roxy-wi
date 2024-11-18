$( function() {
    $("#nettools_nslookup_record_type").selectmenu({
        width: 175
    });
    $("#nettools_telnet_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        var frm = $('#nettools_telnet_form');
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
            data: getFormData(frm),
            type: frm.attr('method'),
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.error(data);
                } else if (data.indexOf('error: ') != '-1' || data.indexOf('Fatal') != '-1' || data.indexOf('Error(s)') != '-1') {
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
        var frm = $('#nettools_nslookup_form');
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
            data: getFormData(frm),
            type: frm.attr('method'),
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.warning(data);
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
        if ($('#nettools_icmp_server_from option:selected').val() === '------') {
            toastr.warning('Choose a server From');
            return false;
        }
        if ($('#nettools_icmp_server_to').val() === '') {
            toastr.warning('Enter a server To');
            return false;
        }
        let data = getFormData(frm);
        data = JSON.parse(data);
        data['action'] = $(this).val();
        $.ajax({
            url: frm.attr('action'),
            data: JSON.stringify(data),
            type: frm.attr('method'),
            contentType: "application/json; charset=utf-8",
            xhrFields: {
                onprogress: function (e) {
                    try {
                        data = JSON.parse(e.currentTarget.responseText);
                        toastr.warning(data.error);
                    } catch (error) {
                        $('#ajax-nettools').html(e.currentTarget.responseText);
                    }
                }
            },
            dataType: 'text',
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.error(data);
                }
            }
        });
        event.preventDefault();
    });
    $("#nettools_portscanner_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        if ($('#nettools_portscanner_server').val() == '') {
            toastr.warning('Enter an address');
            return false;
        }
        $.ajax({
            url: "/portscanner/scan/" + $('#nettools_portscanner_server').val(),
            success: function (data) {
                data = data.replace(/\s+/g, ' ');
                if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
                    toastr.error(data);
                } else {
                    toastr.clear();
                    $("#show_scans_ports_body").html(data);
                    var close_word = $('#translate').attr('data-close');
                    $("#show_scans_ports").dialog({
                        resizable: false,
                        height: "auto",
                        width: 360,
                        modal: true,
                        title: "{{lang.words.opened|title()}} {{lang.words.ports}}",
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
        var frm = $('#nettools_whois_form');
        if ($('#nettools_whois_name').val() == '') {
            toastr.warning('Enter a Domain name');
            return false;
        }
        $.ajax({
            url: frm.attr('action'),
            data: getFormData(frm),
            type: frm.attr('method'),
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.error(data);
                } else {
                    toastr.clear();
                    $('#ajax-nettools').html('<div class="ping_pre">' + data + '</div>');
                }
            }
        });
        event.preventDefault();
    });
    $("#nettools_ipcalc_form").on("click", ":submit", function (e) {
        $('#ajax-nettools').html('');
        let frm = $('#nettools_ipcalc_form');
        let ip = $('#nettools_address').val();
        let netmask = $('#nettools_netmask').val();
        if (ip === '') {
            toastr.warning('Enter a valid IP address');
            return false;
        }
        if (netmask === '') {
            toastr.warning('Enter a valid Netmask');
            return false;
        }
        $.ajax({
            url: frm.attr('action'),
            data: JSON.stringify({'ip': ip, 'netmask': netmask}),
            type: frm.attr('method'),
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.clear();
                    toastr.error(data.error);
                } else {
                    toastr.clear();
                    $('#ajax-nettools').html(
                        '<div class="ping_pre"><b>Address</b>: ' + data.address + '<br />' +
                        '<b>Netmask</b>: ' + data.netmask + '<br />' +
                        '<b>Network</b>: ' + data.network + '<br />' +
                        '<b>Broadcast</b>: ' + data.broadcast + '<br />' +
                        '<b>Host min</b>: ' + data.min + '<br />' +
                        '<b>Host max</b>: ' + data.max + '<br />' +
                        '<b>Hosts</b>: ' + data.hosts +
                        '</div>'
                    );
                }
            }
        });
        event.preventDefault();
    });
});
function getFormData($form){
    let unindexed_array = $form.serializeArray();
    let indexed_array = {};

    $.map(unindexed_array, function(n, i){
        indexed_array[n['name']] = n['value'];
    });

    return JSON.stringify(indexed_array);
}
