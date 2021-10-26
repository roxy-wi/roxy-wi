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
    $('#gcore_create_network_type').on('selectmenuchange', function (){
    	if ($('#gcore_create_network_type option:selected').val() == 'any_subnet') {
    		$('#gcore_any_subnet').show();
		} else if ($('#gcore_create_network_type option:selected').val() == 'external') {
    		$('#gcore_any_subnet').hide();
		}
	});
    $('#gcore_create_regions').on('selectmenuchange', function (){
    	if ($('#gcore_create_regions option:selected').val() == '6' || $('#gcore_create_regions option:selected').val() == '14') {
    		var newOptions = {
    		    "centos-7-gcore": "Centos 7"
    		};
		} else if ($('#gcore_create_regions option:selected').val() == '10') {
    		var newOptions = {
    		    "centos-7-gcore": "Centos 7",
                "sles15-SP2": "SLES 15-SP2"
    		};
		} else if ($('#gcore_create_regions option:selected').val() == '18' || $('#gcore_create_regions option:selected').val() == '22') {
    		var newOptions = {
    		    "centos-7-1811-x64-qcow2": "Centos 7",
    		    "centos8-1911-x64": "Centos 8",
                "sles15-SP2": "SLES 15-SP2",
                "fedora-32-x64-qcow2": "Fedora 32",
                "fedora-33-x64-qcow2": "Fedora 33",
                "fedora-coreos-32-x64": "Fedora CoreOS 32",
                "ubuntu-16.04-x64": "Ubuntu 16.04",
                "ubuntu-18.04-x64": "Ubuntu 18.04",
                "ubuntu-20.04-x64": "Ubuntu 20.04",
                "ubuntu-20.10-x64": "Ubuntu 20.10",
                "debian-9.7-x64-qcow2": "Debian 9.7",
                "debian-10.1-x64-qcow2": "Debian 10.1",
                "debian-10.3-x64-qcow2": "Debian 10.3"
    		};
		}
    	var $el = $("#gcore_create_oss");
        $el.empty();
        $.each(newOptions, function(key,value) {
            $el.append($("<option></option>")
             .attr("value", key).text(value));
        });
        $el.selectmenu("refresh");
	});
    $('#gcore-instance-enter').on('click', function() {
		$('#gcore_create_size').css('display', 'none');
		$('#gcore-instance-enter').css('display', 'none');
		$('#gcore_create_size').attr('id', 'gcore_create_size_select');
		$("#gcore_create_size_select" ).selectmenu( "destroy" );
		$("#gcore_create_size_select" ).css('display', 'none');
		$('#gcore_create_size_text').attr('id', 'gcore_create_size');
		$('#gcore_create_size').css('display', 'inline');
		$('#gcore-instance-enter-select').css('display', 'inline');
	});
    $('#gcore-instance-enter-select').on('click', function() {
		$('#gcore_create_size').css('display', 'none');
		$('#gcore_create_size').attr('id', 'gcore_create_size_text');
		$('#gcore_create_size_select').attr('id', 'gcore_create_size');
		$("#gcore_create_size" ).selectmenu();
		$("#gcore-instance-enter-select" ).css('display', 'none');
		$('#gcore-instance-enter').css('display', 'inline');
	});
    $('#do-instance-enter').on('click', function() {
		$('#do_create_size').css('display', 'none');
		$('#do-instance-enter').css('display', 'none');
		$('#do_create_size').attr('id', 'do_create_size_select');
		$("#do_create_size_select" ).selectmenu( "destroy" );
		$("#do_create_size_select" ).css('display', 'none');
		$('#do_create_size_text').attr('id', 'do_create_size');
		$('#do_create_size').css('display', 'inline');
		$('#do-instance-enter-select').css('display', 'inline');
	});
    $('#do-instance-enter-select').on('click', function() {
		$('#do_create_size').css('display', 'none');
		$('#do_create_size').attr('id', 'do_create_size_text');
		$('#do_create_size_select').attr('id', 'do_create_size');
		$("#do_create_size" ).selectmenu();
		$("#do-instance-enter-select" ).css('display', 'none');
		$('#do-instance-enter').css('display', 'inline');
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
var gcoreProvider = $( "#gcore_provider" ).dialog({
    autoOpen: false,
	width: 574,
	modal: true,
	title: "Add G-Core Labs as provider",
	buttons: {
	    "Add": function() {
            addGcoreProvider($( this ));
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
var gcoreCreate = $( "#gcore_create" ).dialog({
    autoOpen: false,
	width: 574,
	modal: true,
	title: "Create a new Instance in G-Core Labs",
	buttons: {
	    "Create": function() {
            gcoreCreateServer($(this));
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
    } else if (provider == 'gcore') {
        gcoreProvider.dialog('open');
    } else {
        toastr.error('Choose provider before adding');
    }
}
function CreateServer(provider) {
    if (provider == 'aws') {
        awsCreate.dialog('open');
    } else if (provider == 'do') {
        doCreate.dialog('open');
    } else if (provider == 'gcore') {
        gcoreCreate.dialog('open');
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
function gcoreCreateServer(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#gcore_create_server_name') ).add( $('#gcore_create_size') ).add( $('#gcore_create_volume_size') )
        .add( $('#gcore_create_project_name') ).add( $('#gcore_create_ssh_name') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#gcore_create_server_name'), "Server name", 1 );
	valid = valid && checkLength( $('#gcore_create_size'), "Flavor", 1 );
	valid = valid && checkLength( $('#gcore_create_project_name'), "Project", 1 );
	valid = valid && checkLength( $('#gcore_create_ssh_name'), "SSH key pair name", 1 );
	valid = valid && checkLength( $('#gcore_create_volume_size'), "Volume size ", 1 );
	if (valid) {
		clearTips();
	    dialog_id.dialog('close');
	    startCreatingServer('gcore');
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
	    dialog_id.dialog('close');
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
	} else if (provider == 'gcore') {
    	gcoreInitServer();
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
	} else if (provider == 'gcore') {
    	gcoreEditInitServer(server_id);
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
	        aws_create_volume_type: $('#aws_create_volume_type').val(),
	        delete_on_termination: aws_create_delete_on_termination,
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
	        aws_create_volume_type: $('#aws_create_volume_type').val(),
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
                showProvisioningError(data, '#creating-workspace', '#creating-validate', '#wait-mess', '#creating-error', '#creating-progress', 'aws');
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
            var server_id = $('#ajax-provisioning-body tr td span:regex(id, server-ip-)').last().attr('id').split('-')[2]
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
                $('#server-ip-'+server_id).text(data);
				$('#sever-status-'+server_id).css('color', 'var(--green-color)');
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
function awsEditingVarsServer(server_id) {
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
	        aws_editing_volume_type: $('#aws_edit_volume_type').val(),
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
	        aws_editing_volume_type: $('#aws_edit_volume_type').val(),
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
	            $('#server-ip-'+server_id).text(data);
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
function editGcoreServer(id) {
    $.ajax( {
		url: "options.py",
		data: {
			editGcoreServer: id,
            editGcoreGroup: $('#server-group-'+id).text(),
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
			    var gcoreEdit = $( "#gcore_edit" ).dialog({
                    autoOpen: false,
                    width: 576,
                    modal: true,
                    title: "Editing G-Core Labs server: " + $('#server-name-'+id).text(),
					close: function( event, ui ) {$( this ).dialog( "destroy" );},
                    buttons: {
                        "Edit": function() {
                            gcoreEditServer($(this), id);
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
			    gcoreEdit.dialog('open');
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
function add_gcore_button_after_server_created() {
    var buttons = creatingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            gcoreCreate.dialog( "open" );
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
function add_gcore_button_after_server_edited(server_id) {
    var buttons = editingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            editGcoreServer(server_id)
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
function add_gcore_button_after_server_edited(server_id) {
    var buttons = editingServer.dialog("option", "buttons");
    $.extend(buttons, { Back: function() {
            $( this ).dialog( "close" );
            editGcoreServer(server_id);
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
	$(progress_id).css('width', '0%');
	if(cloud == 'aws') {
		add_button_after_server_created();
	} else if (cloud == 'do') {
		add_do_button_after_server_created();
	} else if (cloud == 'gcore') {
		add_gcore_button_after_server_created();
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
    $(progress_id).css('width', progress_value+'%');
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
function addGcoreProvider(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#gcore_new_name') ).add( $('#gcore_new_name')).add( $('#gcore_new_pass') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#gcore_new_name'), "Provider name", 1 );
	valid = valid && checkLength( $('#gcore_new_name'), "User name", 1 );
	valid = valid && checkLength( $('#gcore_new_pass'), "Password", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
			    gcore_new_name: $('#gcore_new_name').val(),
			    gcore_new_group: $('#do_new_group').val(),
			    gcore_new_user: $('#gcore_new_user').val(),
			    gcore_new_pass: $('#gcore_new_pass').val(),
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
					$('select:regex(id, gcore_create_provider)').append('<option value=' + id + '>' +$('#gcore_new_name').val()+'</option>').selectmenu("refresh");
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
    var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#do_edit_provider_name')).add( $('#do_edit_provider_token') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#do_edit_provider_name'), "Provider name", 1 );
	valid = valid && checkLength( $('#do_edit_provider_token'), "Token", 1 );
	if(valid) {
	    doEditProvider.dialog( "close" );
        id = $('#do_edit_provider_id').val();
        token = $('#do_edit_provider_token').val();
        new_name = $('#do_edit_provider_name').val();
        $.ajax({
            url: "options.py",
            data: {
                edit_do_provider: id,
                edit_do_provider_name: new_name,
                edit_do_provider_token: token,
                token: $('#token').val()
            },
            type: "POST",
            success: function (data) {
                data = data.replace(/\s+/g, ' ');
                if (data == "ok ") {
                    $("#provider-name-" + id).text(new_name);
                    $("#provider-" + id).addClass("update", 1000);
                    setTimeout(function () {
                        $("#provider-" + id).removeClass("update");
                    }, 2500);
                    $('#provider-edited-date-' + id).text(returnFormatedDate())
                } else if (data.indexOf('error:') != '-1') {
                    toastr.error(data);
                }
            }
        });
    }
}
var gcoreEditProvider = $( "#gcore_edit_provider" ).dialog({
    autoOpen: false,
    width: 574,
    modal: true,
    title: "Editing G-Core Labs provider",
    buttons: {
        "Edit": function() {
            gcoreEditProviderSave();
        },
        Cancel: function() {
            $( this ).dialog( "close" );
            clearTips();
        }
    }
});
function editGcoreProvider(id) {
    $('#gcore_edit_provider_id').val(id);
    name = $('#provider-name-'+id).text();
    $('#gcore_edit_provider_name').val(name);
    gcoreEditProvider.dialog('open');
}
function gcoreEditProviderSave() {
    var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#gcore_edit_provider_name')).add( $('#gcore_edit_provider_user') ).add( $('#gcore_edit_provider_password'));
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#gcore_edit_provider_name'), "User name", 1 );
	valid = valid && checkLength( $('#gcore_edit_provider_user'), "Provider name", 1 );
	valid = valid && checkLength( $('#gcore_edit_provider_password'), "Password", 1 );
	if(valid) {
	    gcoreEditProvider.dialog('close');
	    clearTips();
        id = $('#gcore_edit_provider_id').val();
        username = $('#gcore_edit_provider_user').val();
        pass = $('#gcore_edit_provider_password').val();
        new_name = $('#gcore_edit_provider_name').val();
        $.ajax({
            url: "options.py",
            data: {
                edit_gcore_provider: id,
                edit_gcore_provider_name: new_name,
                edit_gcore_provider_user: username,
                edit_gcore_provider_pass: pass,
                token: $('#token').val()
            },
            type: "POST",
            success: function (data) {
                data = data.replace(/\s+/g, ' ');
                if (data == "ok ") {
                    $("#provider-name-" + id).text(new_name);
                    $("#provider-" + id).addClass("update", 1000);
                    setTimeout(function () {
                        $("#provider-" + id).removeClass("update");
                    }, 2500);
                    $('#provider-edited-date-' + id).text(returnFormatedDate())
                } else if (data.indexOf('error:') != '-1') {
                    toastr.error(data);
                }
            }
        });
    }
}
var awsEditProvider = $("#aws_edit_provider").dialog({
    autoOpen: false,
    width: 574,
    modal: true,
    title: "Editing AWS provider",
    buttons: {
        "Edit": function () {
            awsEditProviderSave($(this));
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
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#aws_edit_provider_name')).add( $('#aws_edit_provider_key') ).add($('#aws_edit_provider_secret'));
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#aws_edit_provider_name'), "Provider name", 1 );
	valid = valid && checkLength( $('#aws_edit_provider_key'), "ACCESS_KEY", 1 );
	valid = valid && checkLength( $('#aws_edit_provider_secret'), "ACCESS_SECRET", 1 );
	if(valid) {
        awsEditProvider.dialog("close");
        id = $('#aws_edit_provider_id').val();
        new_name = $('#aws_edit_provider_name').val();
        key = $('#aws_edit_provider_key').val();
        secret = $('#aws_edit_provider_secret').val();
        $.ajax({
            url: "options.py",
            data: {
                edit_aws_provider: id,
                edit_aws_provider_name: new_name,
                edit_aws_provider_key: key,
                edit_aws_provider_secret: secret,
                token: $('#token').val()
            },
            type: "POST",
            success: function (data) {
                data = data.replace(/\s+/g, ' ');
                if (data == "ok ") {
                    $("#provider-name-" + id).text(new_name);
                    $("#provider-" + id).addClass("update", 1000);
                    $('#provider-edited-date-' + id).text(returnFormatedDate())
                    setTimeout(function () {
                        $("#provider-" + id).removeClass("update");
                    }, 2500);
                } else if (data.indexOf('error:') != '-1') {
                    toastr.error(data);
                }
            }
        });
    }
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
	            $('#server-ip-'+server_id).text(data);
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
            var server_id = $('#ajax-provisioning-body tr td span:regex(id, server-ip-)').last().attr('id').split('-')[2]
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#creating-server', '#creating-workspace', '#wait-mess', '#creating-error', '#creating-progress', 'do');
                $('#sever-status-'+server_id).text('Error');
                $('#sever-status-'+server_id).attr('title', data);
               	$('#sever-status-'+server_id).css('color', 'red');
            } else {
                showProvisioningProccess('#creating-workspace', '#creating-server', '', '100', '#creating-progress');
                $('#wait-mess').hide();
                $('#created-mess').html('Server has been created. Server IPs are: ' + data);
                $('#created-mess').show();
                $('#sever-status-'+server_id).text('Created');
                $('#server-ip-'+server_id).text(data);
				$('#sever-status-'+server_id).css('color', 'var(--green-color)');
                add_do_button_after_server_created();
            }
        }
    } );
}
function gcoreInitServer() {
    $('#creating-init').addClass('proccessing');
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreinitserver: 1,
		    token: $('#token').val()
		},
		type: "POST",
        success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-init', '#creating-init', '#wait-mess', '#creating-error', '#creating-progress', 'gcore');
            } else {
                showProvisioningProccess('#creating-init', '#creating-init', '#creating-vars', '20', '#creating-progress');
                gcoreVarsServer();
            }
        }
    } );
}
function gcoreVarsServer() {
    var gcore_create_firewall = 'false';
    var gcore_create_delete_on_termination = 'false';
    if ($('#gcore_create_firewall').is(':checked')) {
		gcore_create_firewall = 'true';
	}
    if ($('#gcore_create_delete_on_termination').is(':checked')) {
		gcore_create_delete_on_termination = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        gcorevars: $('#gcore_create_server_name').val(),
	        gcore_create_group: $('#gcore_create_group').val(),
	        gcore_create_provider: $('#gcore_create_provider').val(),
	        gcore_create_regions: $('#gcore_create_regions').val(),
	        gcore_create_project: $('#gcore_create_project_name').val(),
	        gcore_create_size: $('#gcore_create_size').val(),
	        gcore_create_oss: $('#gcore_create_oss').val(),
	        gcore_create_ssh_name: $('#gcore_create_ssh_name').val(),
	        gcore_create_volume_size: $('#gcore_create_volume_size').val(),
	        gcore_create_volume_type: $('#gcore_create_volume_type').val(),
	        gcore_create_delete_on_termination: gcore_create_delete_on_termination,
	        gcore_create_network_name: $('#gcore_create_network_name').val(),
	        gcore_create_firewall: gcore_create_firewall,
	        gcore_create_network_type: $('#gcore_create_network_type').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-vars', '#creating-init', '#wait-mess', '#creating-error', '#creating-progress', 'gcore');
            } else {
                showProvisioningProccess('#creating-init', '#creating-vars', '#creating-validate', '40', '#creating-progress');
                gcoreValidateServer();
            }
        }
    } );
}
function gcoreValidateServer() {
    $.ajax( {
	    url: "options.py",
        data: {
	        gcorevalidate: $('#gcore_create_server_name').val(),
            gcore_create_group: $('#gcore_create_group').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#creating-validate', '#creating-vars', '#wait-mess', '#creating-error', '#creating-progress', 'gcore');
            } else {
                showProvisioningProccess('#creating-vars', '#creating-validate', '#creating-workspace', '60', '#creating-progress');
                gcoreWorkspaceServer();
            }
        }
    } );
}
function gcoreWorkspaceServer() {
    var gcore_create_firewall = 'false';
    var gcore_create_delete_on_termination = 'false';
    if ($('#gcore_create_firewall').is(':checked')) {
		gcore_create_firewall = 'true';
	}
    if ($('#gcore_create_delete_on_termination').is(':checked')) {
		gcore_create_delete_on_termination = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreworkspace: $('#gcore_create_server_name').val(),
	        gcore_create_group: $('#gcore_create_group').val(),
	        gcore_create_provider: $('#gcore_create_provider').val(),
	        gcore_create_regions: $('#gcore_create_regions').val(),
	        gcore_create_project: $('#gcore_create_project_name').val(),
	        gcore_create_size: $('#gcore_create_size').val(),
	        gcore_create_oss: $('#gcore_create_oss').val(),
	        gcore_create_ssh_name: $('#gcore_create_ssh_name').val(),
	        gcore_create_volume_size: $('#gcore_create_volume_size').val(),
	        gcore_create_volume_type: $('#gcore_create_volume_type').val(),
	        gcore_create_delete_on_termination: gcore_create_delete_on_termination,
	        gcore_create_network_name: $('#gcore_create_network_name').val(),
	        gcore_create_firewall: gcore_create_firewall,
	        gcore_create_network_type: $('#gcore_create_network_type').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#creating-workspace', '#creating-validate', '#wait-mess', '#creating-error', '#creating-progress', 'gcore');
            } else {
                showProvisioningProccess('#creating-validate', '#creating-workspace', '#creating-server', '80', '#creating-progress');
                common_ajax_action_after_success('1', 'newserver', 'ajax-provisioning-body', data);
                gcoreProvisiningServer();
            }
        }
    } );
}
function gcoreProvisiningServer() {
	var gcoreprovisining = $('#gcore_create_server_name').val()
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreprovisining: gcoreprovisining,
            gcore_create_group: $('#gcore_create_group').val(),
            gcore_create_provider: $('#gcore_create_provider').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            var server_id = $('#ajax-provisioning-body tr td span:regex(id, server-ip-)').last().attr('id').split('-')[2]
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#creating-server', '#creating-workspace', '#wait-mess', '#creating-error', '#creating-progress', 'gcore');
                $('#sever-status-'+server_id).text('Error');
                $('#sever-status-'+server_id).attr('title', data);
               	$('#sever-status-'+server_id).css('color', 'red');
            } else {
            	data = data.split(':');
            	data[1] = data[1].replace(/\s+/g, ' ');
                showProvisioningProccess('#creating-workspace', '#creating-server', '', '100', '#creating-progress');
                $('#wait-mess').hide();
                $('#created-mess').html('Server has been created. Server IPs are:' + data[0]);
                $('#created-mess').show();
                $('#sever-status-'+server_id).text('Created');
                $('#sever-status-'+server_id).css('color', 'var(--green-color)');
                $('#server-ip-'+server_id).text(data[0]);
                $('#server-name-'+server_id).text(gcoreprovisining+'('+data[1]+')');
                add_gcore_button_after_server_created();
            }
        }
    } );
}
function gcoreEditServer(dialog_id, server_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#gcore_edit_size')).add( $('#gcore_edit_ssh_name')).add( $('#gcore_edit_volume_size'));
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#gcore_edit_size'), "Instance type", 1 );
	valid = valid && checkLength( $('#gcore_edit_ssh_name'), "SSH key pair name", 1 );
	valid = valid && checkLength( $('#gcore_edit_volume_size'), "Volume size", 1 );
	if(valid) {
	    clearTips();
	    dialog_id.dialog('destroy');
	    startEditingServer('gcore', server_id);
	    $('#editing-wait-mess').show();
    }
}
function gcoreEditInitServer(server_id) {
    $('#editing-init').addClass('proccessing');
    $('#server-'+server_id).css('background-color', '#fff3cd');
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreinitserver: 1,
		    token: $('#token').val()
		},
		type: "POST",
        success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-init', '#editing-init', '#editing-wait-mess', '#editing-error', '#editing-progress', 'gcore');
                $('#server-'+server_id).css('background-color', '#fff');
                add_gcore_button_after_server_edited(server_id)
            } else {
                showProvisioningProccess('#editing-init', '#editing-init', '#editing-vars', '20', '#editing-progress');
                gcoreEditingVarsServer(server_id);
            }
        }
    } );
}

function gcoreEditingVarsServer(server_id, dialog_id) {
    var gcore_edit_firewall = 'false';
    var gcore_edit_delete_on_termination = 'false';
    if ($('#gcore_edit_firewall').is(':checked')) {
		gcore_edit_firewall = 'true';
	}
    if ($('#gcore_edit_delete_on_termination').is(':checked')) {
		gcore_edit_delete_on_termination = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreeditvars: $('#gcore_edit_server_name').text(),
	        gcore_edit_group: $('#gcore_edit_group').val(),
	        gcore_edit_provider: $('#gcore_edit_id_provider').val(),
	        gcore_edit_regions: $('#gcore_edit_region').text(),
	        gcore_edit_project: $('#gcore_edit_project_name').text(),
	        gcore_edit_size: $('#gcore_edit_size').val(),
	        gcore_edit_oss: $('#gcore_edit_oss').val(),
	        gcore_edit_ssh_name: $('#gcore_edit_ssh_name').val(),
	        gcore_edit_volume_size: $('#gcore_edit_volume_size').val(),
	        gcore_edit_volume_type: $('#gcore_edit_volume_type').val(),
	        gcore_edit_delete_on_termination: gcore_edit_delete_on_termination,
	        gcore_edit_network_name: $('#gcore_edit_network_name').val(),
	        gcore_edit_firewall: gcore_edit_firewall,
	        gcore_edit_network_type: $('#gcore_edit_network_type').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-vars', '#editing-init', '#editing-wait-mess', '#editing-error', '#editing-progress', 'gcore');
                $('#server-'+server_id).css('background-color', '#fff');
                add_gcore_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-init', '#editing-vars', '#editing-validate', '40', '#editing-progress');
                gcoreEditValidateServer(server_id);
            }
        }
    } );
}
function gcoreEditValidateServer(server_id) {
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreeditvalidate: $('#gcore_edit_server_name').text(),
            gcore_edit_group: $('#gcore_edit_group').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1') {
                showProvisioningError(data, '#editing-validate', '#editing-vars', '#editing-wait-mess', '#editing-error', '#editing-progress', 'gcore');
                $('#server-'+server_id).css('background-color', '#fff');
                add_gcore_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-vars', '#editing-validate', '#editing-workspace', '60', '#editing-progress');
                gcoreEditWorkspaceServer(server_id);
            }
        }
    } );
}
function gcoreEditWorkspaceServer(server_id) {
    var gcore_edit_firewall = 'false';
    var gcore_edit_delete_on_termination = 'false';
    if ($('#gcore_edit_firewall').is(':checked')) {
		gcore_edit_firewall = 'true';
	}
    if ($('#gcore_edit_delete_on_termination').is(':checked')) {
		gcore_edit_delete_on_termination = 'true';
	}
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreeditworkspace: $('#gcore_edit_server_name').text(),
	        gcore_edit_group: $('#gcore_edit_group').val(),
	        gcore_edit_provider: $('#gcore_edit_id_provider').val(),
	        gcore_edit_regions: $('#gcore_edit_region').text(),
	        gcore_edit_project: $('#gcore_edit_project_name').text(),
	        gcore_edit_size: $('#gcore_edit_size').val(),
	        gcore_edit_oss: $('#gcore_edit_oss').val(),
	        gcore_edit_ssh_name: $('#gcore_edit_ssh_name').val(),
	        gcore_edit_volume_size: $('#gcore_edit_volume_size').val(),
	        gcore_edit_volume_type: $('#gcore_edit_volume_type').val(),
	        gcore_edit_delete_on_termination: gcore_edit_delete_on_termination,
	        gcore_edit_network_name: $('#gcore_edit_network_name').val(),
	        gcore_edit_firewall: gcore_edit_firewall,
	        gcore_edit_network_type: $('#gcore_edit_network_type').val(),
			server_id: server_id,
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#editing-workspace', '#editing-validate', '#editing-wait-mess', '#editing-error', '#editing-progress', 'gcore');
                showEditProvisioningError(data, server_id);
                add_gcore_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-validate', '#editing-workspace', '#editing-server', '80', '#editing-progress');
                $('#sever-status-'+server_id).text('Editing');
                $('#sever-status-'+server_id).css('color', '#000');
                gcoreEditProvisiningServer(server_id);
            }
        }
    } );
}
function gcoreEditProvisiningServer(server_id, dialog_id) {
	var gcoreeditgprovisining = $('#gcore_edit_server_name').text();
    $.ajax( {
	    url: "options.py",
        data: {
	        gcoreeditgprovisining: gcoreeditgprovisining,
            gcore_edit_group: $('#gcore_edit_group').val(),
            gcore_edit_provider: $('#gcore_edit_id_provider option:selected').val(),
		    token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' && data.indexOf('Last error:') == '-1') {
                showProvisioningError(data, '#editing-server', '#editing-workspace', '#editing-wait-mess', '#editing-error', '#editing-progress', 'gcore');
                showEditProvisioningError(data, server_id);
                add_gcore_button_after_server_edited(server_id);
            } else {
                showProvisioningProccess('#editing-workspace', '#editing-server', '', '100', '#editing-progress');
                data = data.split(':');
                data[1] = data[1].replace(/\s+/g, ' ');
                $('#editing-wait-mess').hide();
                $('#edited-mess').html('Server has been changed. IPs are: ' + data[0]);
                $('#edited-mess').show();
                $('#sever-status-'+server_id).text('Created');
	            $('#sever-size-'+server_id).text($('#gcore_edit_size').val());
	            $('#sever-os-'+server_id).text($('#gcore_edit_oss').val());
	            $('#server-'+server_id).css('background-color', '#fff');
	            $('#sever-status-'+server_id).css('color', 'var(--green-color)');
	            $('#server-ip-'+server_id).text(data[0]);
	            $('#server-name-'+server_id).text(gcoreeditgprovisining+'('+data[1]+')');
            }
        }
    } );
}
function returnFormatedDate() {
    let date = new Date();
    current_date = date.toISOString().slice(0,10)+' '+date.toTimeString().split(' ')[0]
    return current_date
}
