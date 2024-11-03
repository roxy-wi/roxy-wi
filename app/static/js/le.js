let provides = {'standalone': "Stand alone", 'route53': 'Route53', 'linode': 'Linode', 'cloudflare': 'Cloudflare', 'digitalocean': 'Digitalocean'};
$( function() {
    let typeSelect = $( "#new-le-type" );
    typeSelect.on('selectmenuchange',function()  {
       if (typeSelect.val() === 'standalone') {
            $('.le-standalone').show();
            $('.le-dns').hide();
            $('.le-aws').hide();
       } else if (typeSelect.val() === 'cloudflare' || typeSelect.val() === 'digitalocean' || typeSelect.val() === 'linode') {
           $('.le-standalone').hide();
           $('.le-dns').show();
           $('.le-aws').hide();
       } else if (typeSelect.val() === 'route53' ) {
           $('.le-standalone').hide();
           $('.le-dns').hide();
           $('.le-aws').show();
       }
    });
});
function addLe(dialogId) {
    let domain = $('#new-le-domain').val();
    let email = $('#new-le-email').val();
    let type = $('#new-le-type').val();
    let api_key = '';
    let api_token = $('#new-le-token').val();
    let valid = true;
    let allFields = '';
    if (type === 'standalone') {
        allFields = $([]).add($('#new-le-domain')).add($('#new-le-email'));
        allFields.removeClass("ui-state-error");
        valid = valid && checkLength($('#new-le-email'), "Email", 1);
    }
    if (type === 'cloudflare' || type === 'digitalocean' || type === 'linode') {
        allFields = $([]).add($('#new-le-domain')).add($('#new-le-token'));
        allFields.removeClass("ui-state-error");
        valid = valid && checkLength($('#new-le-token'), "Token", 1);
    }
    if (type === 'route53') {
        allFields = $([]).add($('#new-le-domain')).add($('#new-le-access_key_id')).add($('#new-le-secret_access_key'));
        allFields.removeClass("ui-state-error");
        valid = valid && checkLength($('#new-le-access_key_id'), "Access key ID", 1);
        valid = valid && checkLength($('#new-le-secret_access_key'), "Access key", 1);
    }
    valid = valid && checkLength($('#new-le-domain'), "Domains", 1);
    if ($('#new-le-server_id').val() === '------' || $('#new-le-server_id').val() === null) {
        toastr.warning('Select server firts')
        return false;
    }
    if (!valid) {
        return false;
    }
    if (type === 'standalone') {
        if (!validateEmail(email)) {
            toastr.warning('Invalid email format');
            return false;
        }
    }
    if (type === 'route53') {
        api_key = $('#new-le-access_key_id').val();
        api_token = $('#new-le-secret_access_key').val();
    }
    let domains = [];
    if (domain.includes(',')) {
        domains = domain.split(',').filter(function (item) {
            return item.trim() !== '';
        });
    } else if (domain.includes(' ')) {
        domains = domain.split(' ').filter(function (item) {
            return item.trim() !== '';
        });
    } else {
        domains.push(domain);
    }
    let jsonData = {
        'server_id': $('#new-le-server_id').val(),
        'domains': domains,
        'email': email,
        'type': type,
        'api_key': api_key,
        'api_token': api_token,
        'description': $('#new-le-description').val(),
    }
    $.ajax({
        url: '/service/letsencrypt',
        method: 'POST',
        data: JSON.stringify(jsonData),
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data);
            } else {
                getLe(data['id'], dialogId);
            }
        },
    });
}
function removeLe(leId) {
    $("#lets-" + leId).css("background-color", "#f2dede");
    $.ajax({
        url: '/service/letsencrypt/' + leId,
        method: 'DELETE',
        contentType: "application/json; charset=utf-8",
        statusCode: {
			204: function (xhr) {
				$("#lets-" + leId).remove();
			},
			404: function (xhr) {
				$("#lets-" + leId).remove();
			}
		},
        success: function (data) {
            if (data) {
				if (data.status === "failed") {
					toastr.error(data);
				}
			}
        },
    });
}
function confirmDeleteLe(id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " Let's encrypt?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeLe(id);
			}
		},{
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function openLeDialog() {
    $("#le-add-table").dialog({
        autoOpen: true,
        resizable: false,
        height: "auto",
        width: 500,
        modal: true,
        title: $('#translate').attr('data-create') + " Let's encrypt",
        show: {
            effect: "fade",
            duration: 200
        },
        hide: {
            effect: "fade",
            duration: 200
        },
        buttons: [
			{
				text: $('#translate').attr('data-create'),
				click: function () {
					addLe($(this));
				}
			}, {
				text: cancel_word,
				click: function () {
					$(this).dialog("close");
				}
			}
		]
    });
}
function getLe(leId, dialogId) {
    $.ajax({
        url: '/service/letsencrypt/' + leId + "?recurse=True",
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data);
            } else {
                showLe(data);
                $.getScript(awesome);
                $(dialogId).dialog("close");
            }
        },
    });
}
function getLes() {
    $.ajax({
        url: '/service/letsencrypts?recurse=True',
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data);
            } else {
                $('#le_table_body').empty();
                for (let k in data) {
                    showLe(data[k]);
                }
                $.getScript(awesome);
            }
        },
    });
}
function showLe(data) {
    let list_domains = '';
    for (let d of eval(data['domains'])) {
        list_domains += d + ' ';
        if (d < data['domains'].length - 1) {
            list_domains += ', ';
        }
    }
    let le_tag = elem("tr", {"id":"lets-" + data['id']}, [
	elem("td", {"class":"padding10 first-collumn"}, data['server_id']['hostname']),
	elem("td", {"style": "width: 10%;"}, provides[data['type']]),
	elem("td", {"style": "width: 30%;"}, list_domains),
	elem("td", {"style": "width: 38%;"}, data['description']),
	elem("td", null, [
		elem("a", {"class":"delete","onclick":"confirmDeleteLe("+data['id']+")","title":"Delete","style":"cursor: pointer; width: 5%;"}),
		])
    ])
    $('#le_table_body').append(le_tag);
}
