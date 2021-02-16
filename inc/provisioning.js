$( function() {
    $('#add-provider-button').click(function() {
		addProvidersChoosing.dialog('open');
	});
    $('#create-provider-button').click(function() {
		createProvidersChoosing.dialog('open');
	});
    $('#do_create_ssh_choose').on('selectmenuchange', function (){
    	if ($('#do_create_ssh_choose option:selected').val() == 'ssh_name') {
    		$('#do_create_ssh_name_tr').show();
    		$('#do_create_ssh_ids_tr').hide();
		} else if ($('#do_create_ssh_choose option:selected').val() == 'ssh_ids') {
    		$('#do_create_ssh_name_tr').hide();
    		$('#do_create_ssh_ids_tr').show();
		}
	});
});
var addProvidersChoosing = $( "#add_providers_choosing" ).dialog({
		autoOpen: false,
		width: 250,
		modal: true,
		title: "Add a new provider",
		buttons: {
			"Add": function() {
                addProvider($('#add_select_providers option:selected').val());
                $( this ).dialog( "close" );
                clearTips();
			},
			Cancel: function() {
				$( this ).dialog( "close" );
				clearTips();
			}
		}
	});
var createProvidersChoosing = $( "#create_providers_choosing" ).dialog({
		autoOpen: false,
		width: 250,
		modal: true,
		title: "Choose provider for provisioning",
		buttons: {
			"Choose": function() {
                CreateServer($('#create_select_providers option:selected').val());
                $( this ).dialog( "close" );
                clearTips();
			},
			Cancel: function() {
				$( this ).dialog( "close" );
				clearTips();
			}
		}
	});
var awsProvider = $( "#aws_provider" ).dialog({
	autoOpen: false,
	width: 574,
	modal: true,
	title: "Add AWS as provider",
	buttons: {
	    "Add": function() {
            addAwsProvider($( this ));
            clearTips();
        },
        Cancel: function() {
		    $( this ).dialog( "close" );
			addProvidersChoosing.dialog('open');
			clearTips();
        }
    }
});
var doProvider = $( "#do_provider" ).dialog({
    autoOpen: false,
	width: 574,
	modal: true,
	title: "Add DigitalOcean as provider",
	buttons: {
	    "Add": function() {
            addDoProvider($( this ));
            clearTips();
        },
        Cancel: function() {
            $( this ).dialog( "close" );
            addProvidersChoosing.dialog('open');
            clearTips();
        }
    }
});
var doCreate = $( "#do_create" ).dialog({
    autoOpen: false,
	width: 574,
	modal: true,
	title: "Create a new Droplet in DigitalOcean",
	buttons: {
	    "Create": function() {
            doCreateServer($(this));
            clearTips();
        },
        Cancel: function() {
            $( this ).dialog( "close" );
            createProvidersChoosing.dialog('open');
            clearTips();
        }
    }
});
var awsCreate = $( "#aws_create" ).dialog({
    autoOpen: false,
	width: 574,
	modal: true,
	title: "Create a new Instance in AWS",
	buttons: {
	    "Create": function() {
            awsCreateServer($(this));
        },
        Cancel: function() {
            $( this ).dialog( "close" );
            createProvidersChoosing.dialog('open');
            clearTips();
        }
    }
});
var creatingServer = $( "#server_creating" ).dialog({
    autoOpen: false,
    height: 420,
	width: 574,
	modal: true,
	title: "Server is creating",
	buttons: {
        Close: function() {
            $( this ).dialog( "close" );
            $('#wait-mess').show();
            cleanProvisioningProccess('#server_creating ul li', '#created-mess');
            remove_button_after_server_created();
            hideProvisioningError('#creating-error');
            clearTips();
        }
    }
});
var editingServer = $( "#server_editing" ).dialog({
    autoOpen: false,
    height: 420,
	width: 574,
	modal: true,
	title: "Server is editing",
	buttons: {
        Close: function() {
            $( this ).dialog( "close" );
            $('#editing-wait-mess').show();
            cleanProvisioningProccess('#server_editing ul li', '#edited-mess');
            hideProvisioningError('#editing-error');
            clearTips();
            $('#edited-mess').html('');
            $('#edited-mess').hide();
        }
    }
});
function addProvider(provider) {
    if (provider == 'aws') {
        awsProvider.dialog('open');
    } else if (provider == 'do') {
        doProvider.dialog('open');
    } else {
        toastr.error('Choose provider before adding');
    }
}
function CreateServer(provider) {
    if (provider == 'aws') {
        awsCreate.dialog('open');
    } else if (provider == 'do') {
        doCreate.dialog('open');
    } else {
        toastr.error('Choose provider before creating server');
    }
}
function doCreateServer(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#do_create_server_name') ).add( $('#do_create_size'))
        .add( $('#do_create_regions') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#do_create_server_name'), "Server name", 1 );
	valid = valid && checkLength( $('#do_create_size'), "Droplet size", 1 );
	if (valid) {
		clearTips();
	    dialog_id.dialog('close');
	    startCreatingServer('do');
	}
}
function awsCreateServer(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#aws_create_server_name') ).add( $('#aws_create_size')).add( $('#aws_create_ssh_name'))
        .add( $('#aws_create_volume_size'));
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#aws_create_server_name'), "Server name", 1 );
	valid = valid && checkLength( $('#aws_create_size'), "Instance type", 1 );
	valid = valid && checkLength( $('#aws_create_ssh_name'), "SSH key pair name", 1 );
	valid = valid && checkLength( $('#aws_create_volume_size'), "Volume size", 1 );
	if(valid) {
	    clearTips();
	    dialog_id.dialog('destroy');
	    startCreatingServer('aws');
    }
}
function awsEditServer(dialog_id, server_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#aws_edit_size')).add( $('#aws_edit_ssh_name')).add( $('#aws_edit_volume_size'));
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#aws_edit_size'), "Instance type", 1 );
	valid = valid && checkLength( $('#aws_edit_ssh_name'), "SSH key pair name", 1 );
	valid = valid && checkLength( $('#aws_edit_volume_size'), "Volume size", 1 );
	if(valid) {
	    clearTips();
	    dialog_id.dialog('destroy');
	    startEditingServer('aws', server_id);
	    $('#editing-wait-mess').show();
    }

}
function startCreatingServer(provider) {
    $("#wait-mess").html(wait_mess);
    creatingServer.dialog('open');
    if (provider == 'aws') {
        awsInitServer();
    } else if (provider == 'do') {
    	doInitServer();
	}
    $.getScript("/inc/fontawesome.min.js");
}
function startEditingServer(provider, server_id) {
    $("#editing-wait-mess").html(wait_mess);
    editingServer.dialog('open');
    if (provider == 'aws') {
        awsEditInitServer(server_id);
    } else if (provider == 'do') {
    	doEditInitServer(server_id);
	}
    $.getScript("/inc/fontawesome.min.js");
}
function awsInitServer() {
    $('#creating-init').addClass('proccessing');
    $.ajax( {
	    url: "options.py",
        data: {
	        awsinit: 1,
		    token: $('#token').val()
		},
		type: "POST",
        success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-init', '#creating-init', '#wait-mess', '#creating-error', '#creating-progress', 'aws');
            } else {
                showProvisioningProccess('#creating-init', '#creating-init', '#creating-vars', '20', '#creating-progress');
                awsVarsServer();
            }
        }
    } );
}
function awsVarsServer() {
    var aws_create_floating_net = 'false';
    var aws_create_firewall = 'false';
    var aws_create_public_ip = 'false';
    var aws_create_delete_on_termination = 'false';
    if ($('#aws_create_firewall').is(':checked')) {
		aws_create_firewall = 'true';
	}
    if ($('#aws_create_delete_on_termination').is(':checked')) {
		aws_create_delete_on_termination = 'true';
	}
    if ($('#aws_create_public_ip option:selected').val() == 'public') {
		aws_create_public_ip = 'true';
	} else if ($('#aws_create_public_ip option:selected').val() == 'elastic') {
    	aws_create_floating_net = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        awsvars: $('#aws_create_server_name').val(),
	        aws_create_group: $('#aws_create_group').val(),
	        aws_create_provider: $('#aws_create_provider').val(),
	        aws_create_regions: $('#aws_create_regions').val(),
	        aws_create_size: $('#aws_create_size').val(),
	        aws_create_oss: $('#aws_create_oss').val(),
	        aws_create_ssh_name: $('#aws_create_ssh_name').val(),
	        aws_create_volume_size: $('#aws_create_volume_size').val(),
	        delete_on_termination: delete_on_termination,
	        aws_create_floating_net: aws_create_floating_net,
	        aws_create_firewall: aws_create_firewall,
	        aws_create_public_ip: aws_create_public_ip,
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-vars', '#creating-init', '#wait-mess', '#creating-error', '#creating-progress', 'aws');
            } else {
                showProvisioningProccess('#creating-init', '#creating-vars', '#creating-validate', '40', '#creating-progress');
                awsValidateServer();
            }
        }
    } );
}
function awsValidateServer() {
    $.ajax( {
	    url: "options.py",
        data: {
	        awsvalidate: $('#aws_create_server_name').val(),
            aws_create_group: $('#aws_create_group').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-validate', '#creating-vars', '#wait-mess', '#creating-error', '#creating-progress', 'aws');
            } else {
                showProvisioningProccess('#creating-vars', '#creating-validate', '#creating-workspace', '60', '#creating-progress');
                awsWorkspaceServer();
            }
        }
    } );
}
function awsWorkspaceServer() {
    var aws_create_floating_net = 'false';
    var aws_create_firewall = 'false';
    var aws_create_public_ip = 'false';
    var aws_create_delete_on_termination = 'false';
    if ($('#aws_create_firewall').is(':checked')) {
		aws_create_firewall = 'true';
	}
    if ($('#aws_create_delete_on_termination').is(':checked')) {
		aws_create_delete_on_termination = 'true';
	}
	if ($('#aws_create_public_ip option:selected').val() == 'public') {
		aws_create_public_ip = 'true';
	} else if ($('#aws_create_public_ip option:selected').val() == 'elastic') {
    	aws_create_floating_net = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        awsworkspace: $('#aws_create_server_name').val(),
            aws_create_group: $('#aws_create_group').val(),
	        aws_create_provider: $('#aws_create_provider option:selected').val(),
	        aws_create_regions: $('#aws_create_regions').val(),
	        aws_create_size: $('#aws_create_size').val(),
	        aws_create_oss: $('#aws_create_oss option:selected').val(),
	        aws_create_ssh_name: $('#aws_create_ssh_name').val(),
	        aws_create_volume_size: $('#aws_create_volume_size').val(),
	        aws_create_delete_on_termination: aws_create_delete_on_termination,
	        aws_create_floating_net: aws_create_floating_net,
	        aws_create_firewall: aws_create_firewall,
	        aws_create_public_ip: aws_create_public_ip,
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
            	var server_id = $('#ajax-provisioning-body tr td span:regex(id, sever-ip-)').last().attr('id').split('-')[2]
                showProvisioningError(data, '#creating-workspace', '#creating-validate', '#wait-mess', '#creating-error', '#creating-progress', 'aws');
                $('#sever-status-'+server_id).text('Error');
                $('#sever-status-'+server_id).attr('title', data);
               	$('#sever-status-'+server_id).css('color', 'red');
            } else {
                showProvisioningProccess('#creating-validate', '#creating-workspace', '#creating-server', '80', '#creating-progress');
                common_ajax_action_after_success('1', 'newserver', 'ajax-provisioning-body', data);
                awsProvisiningServer();
            }
        }
    } );
}
function awsProvisiningServer() {
    $.ajax( {
	    url: "options.py",
        data: {
	        awsprovisining: $('#aws_create_server_name').val(),
            aws_create_group: $('#aws_create_group').val(),
            aws_create_provider: $('#aws_create_provider').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            var server_id = $('#ajax-provisioning-body tr td span:regex(id, sever-ip-)').last().attr('id').split('-')[2]
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#creating-server', '#creating-workspace', '#wait-mess', '#creating-error', '#creating-progress', 'aws');
                $('#sever-status-'+server_id).text('Error');
                $('#sever-status-'+server_id).attr('title', data);
               	$('#sever-status-'+server_id).css('color', 'red');
            } else {
                showProvisioningProccess('#creating-workspace', '#creating-server', '', '100', '#creating-progress');
                $('#wait-mess').hide();
                $('#created-mess').html('Server has been created. Server IPs are:' + data);
                $('#created-mess').show();
                $('#sever-status-'+server_id).text('Created');
                $('#sever-ip'+server_id).text(data);
                add_button_after_server_created();
            }
        }
    } );
}
function awsEditInitServer(server_id) {
    $('#editing-init').addClass('proccessing');
    $('#server-'+server_id).css('background-color', '#fff3cd');
    $.ajax( {
	    url: "options.py",
        data: {
	        awsinit: 1,
		    token: $('#token').val()
		},
		type: "POST",
        success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-init', '#editing-init', '#editing-wait-mess', '#editing-error', '#editing-progress', 'aws');
                $('#server-'+server_id).css('background-color', '#fff');
                add_button_after_server_edited(server_id)
            } else {
                showProvisioningProccess('#editing-init', '#editing-init', '#editing-vars', '20', '#editing-progress');
                awsEditingVarsServer(server_id);
            }
        }
    } );
}
function awsEditingVarsServer(server_id, dialog_id) {
    var aws_edit_floating_net = 'false';
    var aws_editing_firewall = 'false';
    var aws_edit_public_ip = 'false';
    var aws_edit_delete_on_termination = 'false';
    if ($('#aws_edit_firewall').is(':checked')) {
		aws_editing_firewall = 'true';
	}
    if ($('#aws_edit_delete_on_termination').is(':checked')) {
		aws_edit_delete_on_termination = 'true';
	}
    if ($('#aws_edit_public_ip option:selected').val() == 'public') {
		aws_edit_public_ip = 'true';
	} else if ($('#aws_edit_public_ip option:selected').val() == 'elastic') {
    	aws_edit_floating_net = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        awseditvars: $('#aws_edit_server_name').text(),
	        aws_editing_group: $('#aws_edit_group').val(),
	        aws_editing_provider: $('#aws_edit_id_provider option:selected').val(),
	        aws_editing_regions: $('#aws_edit_region').text(),
	        aws_editing_size: $('#aws_edit_size').val(),
	        aws_editing_oss: $('#aws_edit_oss option:selected').val(),
	        aws_editing_ssh_name: $('#aws_edit_ssh_name').val(),
	        aws_editing_volume_size: $('#aws_edit_volume_size').val(),
	        aws_editing_delete_on_termination: aws_edit_delete_on_termination,
	        aws_editing_floating_net: aws_edit_floating_net,
	        aws_editing_firewall: aws_editing_firewall,
	        aws_editing_public_ip: aws_edit_public_ip,
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-vars', '#editing-init', '#editing-wait-mess', '#editing-error', '#editing-progress', 'aws');
                $('#server-'+server_id).css('background-color', '#fff');
                add_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-init', '#editing-vars', '#editing-validate', '40', '#editing-progress');
                awsEditValidateServer(server_id);
            }
        }
    } );
}
function awsEditValidateServer(server_id) {
    $.ajax( {
	    url: "options.py",
        data: {
	        awseditvalidate: $('#aws_edit_server_name').text(),
            aws_edit_group: $('#aws_edit_group').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-validate', '#editing-vars', '#editing-wait-mess', '#editing-error', '#editing-progress', 'aws');
                $('#server-'+server_id).css('background-color', '#fff');
                add_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-vars', '#editing-validate', '#editing-workspace', '60', '#editing-progress');
                awsEditWorkspaceServer(server_id);
            }
        }
    } );
}
function awsEditWorkspaceServer(server_id) {
    var aws_edit_floating_net = 'false';
    var aws_editing_firewall = 'false';
    var aws_edit_public_ip = 'false';
    var aws_edit_delete_on_termination = 'false';
    if ($('#aws_edit_firewall').is(':checked')) {
		aws_editing_firewall = 'true';
	}
    if ($('#aws_edit_delete_on_termination').is(':checked')) {
		aws_edit_delete_on_termination = 'true';
	}
    if ($('#aws_edit_public_ip option:selected').val() == 'public') {
		aws_edit_public_ip = 'true';
	} else if ($('#aws_edit_public_ip option:selected').val() == 'elastic') {
    	aws_edit_floating_net = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        awseditworkspace: $('#aws_edit_server_name').text(),
	        aws_editing_group: $('#aws_edit_group').val(),
	        aws_editing_provider: $('#aws_edit_id_provider option:selected').val(),
	        aws_editing_regions: $('#aws_edit_region').text(),
	        aws_editing_size: $('#aws_edit_size').val(),
	        aws_editing_oss: $('#aws_edit_oss option:selected').val(),
	        aws_editing_ssh_name: $('#aws_edit_ssh_name').val(),
	        aws_editing_volume_size: $('#aws_edit_volume_size').val(),
	        aws_editing_delete_on_termination: aws_edit_delete_on_termination,
	        aws_editing_floating_net: aws_edit_floating_net,
	        aws_editing_firewall: aws_editing_firewall,
	        aws_editing_public_ip: aws_edit_public_ip,
            server_id: server_id,
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#editing-workspace', '#editing-validate', '#editing-wait-mess', '#editing-error', '#editing-progress', 'aws');
                showEditProvisioningError(data, server_id);
                add_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-validate', '#editing-workspace', '#editing-server', '80', '#editing-progress');
                $('#sever-status-'+server_id).text('Editing');
                $('#sever-status-'+server_id).css('color', '#000');
                awsEditProvisiningServer(server_id);
            }
        }
    } );
}
function awsEditProvisiningServer(server_id, dialog_id) {
    $.ajax( {
	    url: "options.py",
        data: {
	        awseditingprovisining: $('#aws_edit_server_name').text(),
            aws_edit_group: $('#aws_edit_group').val(),
            aws_edit_provider: $('#aws_edit_id_provider option:selected').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#editing-server', '#editing-workspace', '#editing-wait-mess', '#editing-error', '#editing-progress', 'aws');
                showEditProvisioningError(data, server_id);
                add_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-workspace', '#editing-server', '', '100', '#editing-progress');
                $('#editing-wait-mess').hide();
                $('#edited-mess').html('Server has been changed. IPs are: ' + data);
                $('#edited-mess').show();
                $('#sever-status-'+server_id).text('Created');
	            $('#sever-size-'+server_id).text($('#aws_edit_size').val());
	            $('#sever-os-'+server_id).text($('#aws_edit_oss').val());
	            $('#server-'+server_id).css('background-color', '#fff');
	            $('#sever-status-'+server_id).css('color', '#000');
	            $('#sever-ip-'+server_id).text(data);
            }
        }
    } );
}
function confirmDeleteProvisionedServer(id) {
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#server-name-'+id).text() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );
			deleteProvisionedServer(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function deleteProvisionedServer(id) {
	$("#server-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			provisiningdestroyserver: id,
			servername: $('#server-name-'+id).text(),
			type: $('#server-cloud-'+id).text(),
			provider_id: $('#server-provider-'+id).text(),
			group: $('#server-group-'+id).text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "ok ") {
				$("#server-"+id).remove();
			} else if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.clear();
				toastr.warning(data);
			}
		}
	} );
}
function editAwsServer(id) {
    $.ajax( {
		url: "options.py",
		data: {
			editAwsServer: id,
            editAwsGroup: $('#server-group-'+id).text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.clear();
				toastr.warning(data);
			} else {
			    $('#ajax').html(data);
			    var awsEdit = $( "#aws_edit" ).dialog({
                    autoOpen: false,
                    width: 576,
                    modal: true,
                    title: "Editing AWS server: " + $('#server-name-'+id).text(),
					close: function( event, ui ) {$( this ).dialog( "destroy" );},
                    buttons: {
                        "Edit": function() {
                            awsEditServer($(this), id);
                        },
                        Cancel: function() {
                            $( this ).dialog( "destroy" );
                            clearTips();
                        }
                    }
                });
			    $( "select" ).selectmenu();
			    $( "input[type=checkbox]" ).checkboxradio();
			    $.getScript("/inc/fontawesome.min.js");
			    awsEdit.dialog('open');
            }
		}
	} );
}
function editDoServer(id) {
    $.ajax( {
		url: "options.py",
		data: {
			editDoServer: id,
            editDoGroup: $('#server-group-'+id).text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.clear();
				toastr.warning(data);
			} else {
			    $('#ajax').html(data);
			    var doEdit = $( "#do_edit" ).dialog({
                    autoOpen: false,
                    width: 576,
                    modal: true,
                    title: "Editing Do server: " + $('#server-name-'+id).text(),
					close: function( event, ui ) {$( this ).dialog( "destroy" );},
                    buttons: {
                        "Edit": function() {
                            doEditServer($(this), id);
                        },
                        Cancel: function() {
                            $( this ).dialog( "destroy" );
                            clearTips();
                        }
                    }
                });
			    $( "select" ).selectmenu();
			    $( "input[type=checkbox]" ).checkboxradio();
			    $.getScript("/inc/fontawesome.min.js");
			    doEdit.dialog('open');
            }
		}
	} );
}
function add_button_after_server_created() {
    var buttons = creatingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            awsCreate.dialog( "open" );
            cleanProvisioningProccess('#server_creating ul li', '#created-mess');
            $('#wait-mess').show();
            $('#edited-mess').html('');
            $('#edited-mess').hide();
            hideProvisioningError('#creating-error');
        } });
    creatingServer.dialog("option", "buttons", buttons);
}
function add_do_button_after_server_created() {
    var buttons = creatingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            doCreate.dialog( "open" );
			cleanProvisioningProccess('#server_creating ul li', '#created-mess');
            $('#wait-mess').show();
            $('#edited-mess').html('');
            $('#edited-mess').hide();
            hideProvisioningError('#creating-error');
        } });
    creatingServer.dialog("option", "buttons", buttons);
}
function add_button_after_server_edited(server_id) {
    var buttons = editingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            editAwsServer(server_id)
            cleanProvisioningProccess('#server_editing ul li', '#edited-mess');
            $('#wait-mess').show();
            $('#edited-mess').html('');
            $('#edited-mess').hide();
            hideProvisioningError('#editing-error');
        } });
    editingServer.dialog("option", "buttons", buttons);
}
function add_do_button_after_server_edited(server_id) {
    var buttons = editingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            editDoServer(server_id);
            cleanProvisioningProccess('#server_editing ul li', '#edited-mess');
            $('#wait-mess').show();
            $('#edited-mess').html('');
            $('#edited-mess').hide();
            hideProvisioningError('#editing-error');
        } });
    editingServer.dialog("option", "buttons", buttons);
}
function remove_button_after_server_created() {
    creatingServer.dialog("option",{buttons:{ Close: function() {
            $( this ).dialog( "close" );
            $('#creating-error').hide();
            $('#wait-mess').show();
            cleanProvisioningProccess('#server_creating ul li', 'created-mess');
            clearTips();
        }}}
    );
}
function hideProvisioningError(error_id) {
    $(error_id).html('');
	$(error_id).hide();
}
function showProvisioningError(data, step_id, prev_step_id, wait_mess, error_id, progress_id, cloud, step, server_id) {
    $(wait_mess).hide();
    $(error_id).html(data);
	$(error_id).show();
	$(prev_step_id).removeClass('proccessing');
	$(step_id).addClass('processing_error');
	$(progress_id).val('0');
	if(cloud == 'aws') {
		add_button_after_server_created();
	} else if (cloud == 'do') {
		add_do_button_after_server_created();
	}
	$.getScript("/inc/fontawesome.min.js");
}
function showEditProvisioningError(data, server_id){
	$('#server-'+server_id).css('background-color', '#fff');
	$('#sever-status-'+server_id).text('Error');
	$('#sever-status-'+server_id).attr('title', data);
	$('#sever-status-'+server_id).css('color', 'red');
	$('#sever-status-'+server_id).css('cursor', 'help');
}
function showProvisioningProccess(prev_step_id, step_id, next_step_id, progress_value, progress_id) {
    $(prev_step_id).removeClass('proccessing');
    $(step_id).addClass('proccessing_done');
    $(step_id).removeClass('proccessing');
    $(next_step_id).addClass('proccessing');
    $(progress_id).val(progress_value);
    $.getScript("/inc/fontawesome.min.js");
}
function cleanProvisioningProccess(div_id, success_div) {
    $(success_div).hide();
    $(div_id).each(function () {
        $(this).removeClass('proccessing_done');
        $(this).removeClass('processing_error');
        $(this).removeClass('proccessing');
    });
    $.getScript("/inc/fontawesome.min.js");
}
function addDoProvider(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#do_new_name') ).add( $('#do_new_group')).add( $('#do_new_token') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#do_new_name'), "Provider name", 1 );
	valid = valid && checkLength( $('#do_new_group'), "Group", 1 );
	valid = valid && checkLength( $('#do_new_token'), "Token", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
			    do_new_name: $('#do_new_name').val(),
			    do_new_group: $('#do_new_group').val(),
			    do_new_token: $('#do_new_token').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var getId = new RegExp('[0-9]+');
					var id = data.match(getId);
					$('select:regex(id, do_create_provider)').append('<option value=' + id + '>' +$('#do_new_name').val()+'</option>').selectmenu("refresh");
					common_ajax_action_after_success(dialog_id, 'newprovider', 'ajax-providers', data);
				}
			}
		} );
	}
}
function addAwsProvider(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#aws_new_name') ).add( $('#aws_new_key') ).add( $('#aws_new_secret') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#aws_new_name'), "Provider name", 1 );
	valid = valid && checkLength( $('#aws_new_key'), "ACCESS_KEY", 1 );
	valid = valid && checkLength( $('#aws_new_secret'), "SECRET_KEY", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
			    aws_new_name: $('#aws_new_name').val(),
			    aws_new_group: $('#aws_new_group').val(),
			    aws_new_key: $('#aws_new_key').val(),
			    aws_new_secret: $('#aws_new_secret').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var getId = new RegExp('[0-9]+');
					var id = data.match(getId);
					$('select:regex(id, aws_create_provider)').append('<option value=' + id + '>' +$('#aws_new_name').val()+'</option>').selectmenu("refresh");
					common_ajax_action_after_success(dialog_id, 'newprovider', 'ajax-providers', data);
				}
			}
		} );
	}
}
function confirmDeleteProvider(id) {
	 $( "#dialog-confirm" ).dialog({
      width: 400,
      modal: true,
	  title: "Are you sure you want to delete " +$('#provider-name-'+id).val() + "?",
      buttons: {
        "Delete": function() {
			$( this ).dialog( "close" );
			removeProvider(id);
        },
        Cancel: function() {
			$( this ).dialog( "close" );
        }
      }
    });
}
function removeProvider(id) {
	$("#provider-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			providerdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#provider-"+id).remove();
			} else if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
var doEditProvider = $( "#do_edit_provider" ).dialog({
    autoOpen: false,
    width: 574,
    modal: true,
    title: "Editing DigitalOcean provider",
    buttons: {
        "Edit": function() {
            doEditProviderSave();
            $( this ).dialog( "close" );
        },
        Cancel: function() {
            $( this ).dialog( "close" );
            clearTips();
        }
    }
});
function editDoProvider(id) {
    $('#do_edit_provider_id').val(id);
    name = $('#provider-name-'+id).text();
    $('#do_edit_provider_name').val(name);
    doEditProvider.dialog('open');
}
function doEditProviderSave() {
    id = $('#do_edit_provider_id').val();
    token = $('#do_edit_provider_token').val();
    new_name = $('#do_edit_provider_name').val();
    $.ajax( {
		url: "options.py",
		data: {
			edit_do_provider: id,
			edit_do_provider_name: new_name,
			edit_do_provider_token: token,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "ok ") {
				$("#provider-name-"+id).text(new_name);
				$("#provider-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#provider-"+id ).removeClass( "update" );
				}, 2500 );
                $('#provider-edited-date-'+id).text(returnFormatedDate())
			} else if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
var awsEditProvider = $("#aws_edit_provider").dialog({
    autoOpen: false,
    width: 574,
    modal: true,
    title: "Editing AWS provider",
    buttons: {
        "Edit": function () {
            awsEditProviderSave($(this));
            $( this ).dialog( "close" );
        },
        Cancel: function () {
            $(this).dialog("close");
            clearTips();
        }
    }
});
function editAwsProvider(id) {
    $('#aws_edit_provider_id').val(id);
    name = $('#provider-name-' + id).text();
    $('#aws_edit_provider_name').val(name);
    awsEditProvider.dialog('open');
}
function awsEditProviderSave() {
    id = $('#aws_edit_provider_id').val();
    new_name = $('#aws_edit_provider_name').val();
    key = $('#aws_edit_provider_key').val();
    secret = $('#aws_edit_provider_secret').val();
    $.ajax( {
		url: "options.py",
		data: {
			edit_aws_provider: id,
			edit_aws_provider_name: new_name,
			edit_aws_provider_key: key,
			edit_aws_provider_secret: secret,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "ok ") {
				$("#provider-name-"+id).text(new_name);
				$("#provider-"+id).addClass( "update", 1000 );
                $('#provider-edited-date-'+id).text(returnFormatedDate())
				setTimeout(function() {
					$( "#provider-"+id ).removeClass( "update" );
				}, 2500 );
			} else if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function doEditServer(dialog_id, server_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#do_edit_size'));
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#do_edit_size'), "Droplet size", 1 );
	if (valid) {
		clearTips();
	    dialog_id.dialog('destroy');
	    startEditingServer('do', server_id);
	    $('#editing-wait-mess').show();
	}
}
function doInitServer() {
    $('#creating-init').addClass('proccessing');
    $.ajax( {
	    url: "options.py",
        data: {
	        doinit: 1,
		    token: $('#token').val()
		},
		type: "POST",
        success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-init', '#creating-init', '#wait-mess', '#creating-error', '#creating-progress', 'do');
            } else {
                showProvisioningProccess('#creating-init', '#creating-init', '#creating-vars', '20', '#creating-progress');
                doVarsServer();
            }
        }
    } );
}

function doEditInitServer(server_id) {
    $('#editing-init').addClass('proccessing');
    $('#server-'+server_id).css('background-color', '#fff3cd');
    $.ajax( {
	    url: "options.py",
        data: {
	        doinit: 1,
		    token: $('#token').val()
		},
		type: "POST",
        success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-init', '#editing-init', '#editing-wait-mess', '#editing-error', '#editing-progress', 'do');
                $('#server-'+server_id).css('background-color', '#fff');
                add_do_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-init', '#editing-init', '#editing-vars', '20', '#editing-progress');
                doEditVarsServer(server_id);
            }
        }
    } );
}
function doEditVarsServer(server_id) {
	var do_edit_private_net = 'false';
	var do_edit_floating_net = 'false';
	var do_edit_monitoring = 'false';
	var do_edit_backup = 'false';
	var do_edit_firewall = 'false';
	if ($('#do_edit_private_networking').is(':checked')) {
		do_edit_private_net = 'true';
	}
	if ($('#do_edit_floating_ip').is(':checked')) {
		do_edit_floating_net = 'true';
	}
	if ($('#do_edit_monitoring').is(':checked')) {
		do_edit_monitoring = 'true';
	}
	if ($('#do_edit_backup').is(':checked')) {
		do_edit_backup = 'true';
	}
	if ($('#do_edit_firewall').is(':checked')) {
		do_edit_firewall = 'true';
	}
	$.ajax({
		url: "options.py",
		data: {
			doeditvars: $('#do_edit_server_name').text(),
			do_edit_group: $('#do_edit_group').val(),
			do_edit_provider: $('#do_edit_id_provider').val(),
			do_edit_regions: $('#do_edit_regions').text(),
			do_edit_size: $('#do_edit_size').val(),
			do_edit_oss: $('#do_edit_oss').val(),
			do_edit_ssh_name: $('#do_edit_ssh_name').val(),
			do_edit_ssh_ids: $('#do_edit_ssh_ids').val(),
			do_edit_backup: do_edit_backup,
			do_edit_private_net: do_edit_private_net,
			do_edit_floating_net: do_edit_floating_net,
			do_edit_monitoring: do_edit_monitoring,
			do_edit_firewall: do_edit_firewall,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				showProvisioningError(data, '#editing-vars', '#editing-init', '#editing-wait-mess', '#editing-error', '#editing-progress', 'do');
				$('#server-'+server_id).css('background-color', '#fff');
				add_do_button_after_server_edited(server_id);
			} else {
				showProvisioningProccess('#editing-init', '#editing-vars', '#editing-validate', '40', '#editing-progress');
				doEditValidateServer(server_id)
			}
		}
	});
}
function doEditValidateServer(server_id) {
    $.ajax( {
	    url: "options.py",
        data: {
	        doeditvalidate: $('#do_edit_server_name').text(),
            do_edit_group: $('#do_edit_group').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-validate', '#editing-vars', '#editing-wait-mess', '#editing-error', '#editing-progress', 'do');
            	$('#server-'+server_id).css('background-color', '#fff');
            	add_do_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-vars', '#editing-validate', '#editing-workspace', '60', '#editing-progress');
                doEditWorkspaceServer(server_id);
            }
        }
    } );
}
function doEditWorkspaceServer(server_id) {
    var do_edit_private_net = 'false';
	var do_edit_floating_net = 'false';
	var do_edit_monitoring = 'false';
	var do_edit_backup = 'false';
	var do_edit_firewall = 'false';
	if ($('#do_edit_private_networking').is(':checked')) {
		do_edit_private_net = 'true';
	}
	if ($('#do_edit_floating_ip').is(':checked')) {
		do_edit_floating_net = 'true';
	}
	if ($('#do_edit_monitoring').is(':checked')) {
		do_edit_monitoring = 'true';
	}
	if ($('#do_edit_backup').is(':checked')) {
		do_edit_backup = 'true';
	}
	if ($('#do_edit_firewall').is(':checked')) {
		do_edit_firewall = 'true';
	}
	$.ajax({
		url: "options.py",
		data: {
			doeditworkspace: $('#do_edit_server_name').text(),
			do_edit_group: $('#do_edit_group').val(),
			do_edit_provider: $('#do_edit_id_provider').val(),
			do_edit_regions: $('#do_edit_regions').text(),
			do_edit_size: $('#do_edit_size').val(),
			do_edit_oss: $('#do_edit_oss').val(),
			do_edit_ssh_name: $('#do_edit_ssh_name').val(),
			do_edit_ssh_ids: $('#do_edit_ssh_ids').val(),
			do_edit_private_net: do_edit_private_net,
			do_edit_floating_net: do_edit_floating_net,
			do_edit_monitoring: do_edit_monitoring,
			do_edit_backup: do_edit_backup,
			do_edit_firewall: do_edit_firewall,
			server_id: server_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#editing-workspace', '#editing-validate', '#editing-wait-mess', '#editing-error', '#editing-progress', 'do');
				showEditProvisioningError(data, server_id);
				add_do_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-validate', '#editing-workspace', '#editing-server', '80', '#editing-progress');
                $('#sever-status-'+server_id).text('Editing');
                $('#sever-status-'+server_id).css('color', '#000');
                doEditProvisiningServer(server_id);
            }
        }
    } );
}
function doEditProvisiningServer(server_id) {
    $.ajax( {
	    url: "options.py",
        data: {
	        doeditprovisining: $('#do_edit_server_name').text(),
			do_edit_group: $('#do_edit_group').val(),
			do_edit_provider: $('#do_edit_id_provider').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#editing-server', '#editing-workspace', '#editing-wait-mess', '#editing-error', '#editing-progress', 'do');
                showEditProvisioningError(data, server_id);
				add_do_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-workspace', '#editing-server', '', '100', '#editing-progress');
                $('#editing-wait-mess').hide();
                $('#edited-mess').html('Server has been changed. IPs are: ' + data);
                $('#edited-mess').show();
                $('#sever-status-'+server_id).text('Created');
	            $('#sever-size-'+server_id).text($('#aws_edit_size').val());
	            $('#sever-os-'+server_id).text($('#aws_edit_oss').val());
	            $('#server-'+server_id).css('background-color', '#fff');
	            $('#sever-ip-'+server_id).text(data);
            }
        }
    } );
}
function doVarsServer() {
	var do_create_private_net = 'false';
	var do_create_floating_net = 'false';
	var do_create_monitoring = 'false';
	var do_create_backup = 'false';
	var do_create_firewall = 'false';
	if ($('#do_create_private_net').is(':checked')) {
		do_create_private_net = 'true';
	}
	if ($('#do_create_floating_net').is(':checked')) {
		do_create_floating_net = 'true';
	}
	if ($('#do_create_monitoring').is(':checked')) {
		do_create_monitoring = 'true';
	}
	if ($('#do_create_backup').is(':checked')) {
		do_create_backup = 'true';
	}
	if ($('#do_create_backup').is(':checked')) {
		do_create_firewall = 'true';
	}
	$.ajax({
		url: "options.py",
		data: {
			dovars: $('#do_create_server_name').val(),
			do_create_group: $('#do_create_group').val(),
			do_create_provider: $('#do_create_provider').val(),
			do_create_regions: $('#do_create_regions').val(),
			do_create_size: $('#do_create_size').val(),
			do_create_oss: $('#do_create_oss').val(),
			do_create_ssh_name: $('#do_create_ssh_name').val(),
			do_create_ssh_ids: $('#do_create_ssh_ids').val(),
			do_create_backup: do_create_backup,
			do_create_private_net: do_create_private_net,
			do_create_floating_net: do_create_floating_net,
			do_create_monitoring: do_create_monitoring,
			do_create_firewall: do_create_firewall,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				showProvisioningError(data, '#creating-vars', '#creating-init', '#wait-mess', '#creating-error', '#creating-progress', 'do');
			} else {
				showProvisioningProccess('#creating-init', '#creating-vars', '#creating-validate', '40', '#creating-progress');
				doValidateServer();
			}
		}
	});
}
function doValidateServer() {
    $.ajax( {
	    url: "options.py",
        data: {
	        dovalidate: $('#do_create_server_name').val(),
            do_create_group: $('#do_create_group').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-validate', '#creating-vars', '#wait-mess', '#creating-error', '#creating-progress', 'do');
            } else {
                showProvisioningProccess('#creating-vars', '#creating-validate', '#creating-workspace', '60', '#creating-progress');
                doWorkspaceServer();
            }
        }
    } );
}
function doWorkspaceServer() {
    var do_create_private_net = 'false';
	var do_create_floating_net = 'false';
	var do_create_monitoring = 'false';
	var do_create_backup = 'false';
	var do_create_firewall = 'false';
	if ($('#do_create_private_net').is(':checked')) {
		do_create_private_net = 'true';
	}
	if ($('#do_create_floating_net').is(':checked')) {
		do_create_floating_net = 'true';
	}
	if ($('#do_create_monitoring').is(':checked')) {
		do_create_monitoring = 'true';
	}
	if ($('#do_create_backup').is(':checked')) {
		do_create_backup = 'true';
	}
	if ($('#do_create_backup').is(':checked')) {
		do_create_firewall = 'true';
	}
	$.ajax({
		url: "options.py",
		data: {
			doworkspace: $('#do_create_server_name').val(),
			do_create_group: $('#do_create_group').val(),
			do_create_provider: $('#do_create_provider').val(),
			do_create_regions: $('#do_create_regions').val(),
			do_create_size: $('#do_create_size').val(),
			do_create_oss: $('#do_create_oss').val(),
			do_create_ssh_name: $('#do_create_ssh_name').val(),
			do_create_ssh_ids: $('#do_create_ssh_ids').val(),
			do_create_backup: do_create_backup,
			do_create_private_net: do_create_private_net,
			do_create_floating_net: do_create_floating_net,
			do_create_monitoring: do_create_monitoring,
			do_create_firewall: do_create_firewall,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#creating-workspace', '#creating-validate', '#wait-mess', '#creating-error', '#creating-progress', 'do');
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().text('Error');
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().attr('title', data);
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().css('color', 'red');
            } else {
                showProvisioningProccess('#creating-validate', '#creating-workspace', '#creating-server', '80', '#creating-progress');
                common_ajax_action_after_success('1', 'newserver', 'ajax-provisioning-body', data);
                doProvisiningServer();
            }
        }
    } );
}
function doProvisiningServer() {
    $.ajax( {
	    url: "options.py",
        data: {
	        doprovisining: $('#do_create_server_name').val(),
			do_create_group: $('#do_create_group').val(),
			do_create_provider: $('#do_create_provider').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#creating-server', '#creating-workspace', '#wait-mess', '#creating-error', '#creating-progress', 'do');
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().text('Error');
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().attr('title', data);
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().css('color', 'red');
            } else {
                showProvisioningProccess('#creating-workspace', '#creating-server', '', '100', '#creating-progress');
                $('#wait-mess').hide();
                $('#created-mess').html('Server has been created. Server IPs are: ' + data);
                $('#created-mess').show();
                $('#ajax-provisioning-body tr td span:regex(id, sever-status-)').last().text('Created');
                $('#ajax-provisioning-body tr td span:regex(id, sever-ip-)').last().text(data);
                add_do_button_after_server_created();
            }
        }
    } );
}
function returnFormatedDate() {
    let date = new Date();
    current_date = date.toISOString().slice(0,10)+' '+date.toTimeString().split(' ')[0]
    return current_date
}