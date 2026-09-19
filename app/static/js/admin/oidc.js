(function () {
    'use strict';

    let providers = [];
    let mappings = [];
    let selectedMappingProvider = null;
    let providerDialog;
    let mappingsDialog;
    let mappingDialog;
    let restoreMappingsDialog = false;
    let preserveMappingsStateOnClose = false;
    const translations = JSON.parse(document.getElementById('oidc-translations').textContent);

    function translate(key, values) {
        let message = translations[key] || key;
        Object.keys(values || {}).forEach(function (name) {
            message = message.split('{' + name + '}').join(values[name]);
        });
        return message;
    }

    function actionMenu(items, table) {
		const icons = {
			map: 'fa-sitemap',
			edit: 'fa-edit',
			delete: 'fa-trash-alt'
		};
		const label = table.data('actions-label') || 'Actions';
		const wrapper = $('<div>').addClass('admin-actions');
		const toggle = $('<button type="button">')
			.addClass('rw-icon-button admin-actions-toggle')
			.attr({'title': label, 'aria-label': label, 'aria-haspopup': 'menu', 'aria-expanded': 'false'})
			.append($('<i aria-hidden="true">').addClass('fas fa-ellipsis-v'));
		const menu = $('<div role="menu" hidden>').addClass('admin-actions-menu');

		items.forEach(function (item) {
			$('<button type="button">')
				.addClass('admin-action-item' + (item.danger ? ' admin-action-item-danger' : ''))
				.append(
					$('<i aria-hidden="true">').addClass('fas ' + icons[item.icon]),
					$('<span>').text(item.title)
				)
				.on('click', item.handler)
				.appendTo(menu);
		});

		return wrapper.append(toggle, menu);
    }

    function refreshIcons(container) {
        if (window.FontAwesome && window.FontAwesome.dom) {
            window.FontAwesome.dom.i2svg({node: container[0]});
        }
    }

    function responseError(xhr) {
        const response = xhr.responseJSON || {};
        if (Array.isArray(response.details) && response.details.length) {
            return response.details.map(function (item) {
                return (item.field ? item.field + ': ' : '') + item.message;
            }).join('<br>');
        }
        return response.error || response.message || translations.request_failed;
    }

    function nullableValue(selector) {
        const value = $(selector).val().trim();
        return value || null;
    }

    function providerPayload() {
        return {
            slug: $('#oidc-slug').val().trim(),
            label: $('#oidc-label').val().trim(),
            enabled: $('#oidc-enabled').is(':checked'),
            client_id: $('#oidc-client-id').val().trim(),
            client_secret: $('#oidc-client-secret').val(),
            metadata_url: nullableValue('#oidc-metadata-url'),
            issuer: nullableValue('#oidc-issuer'),
            authorization_endpoint: nullableValue('#oidc-authorization-endpoint'),
            token_endpoint: nullableValue('#oidc-token-endpoint'),
            userinfo_endpoint: nullableValue('#oidc-userinfo-endpoint'),
            jwks_uri: nullableValue('#oidc-jwks-uri'),
            scope: $('#oidc-scope').val().trim(),
            subject_claim: $('#oidc-subject-claim').val().trim(),
            email_claim: $('#oidc-email-claim').val().trim(),
            username_claim: $('#oidc-username-claim').val().trim(),
            groups_claim: $('#oidc-groups-claim').val().trim(),
            allowed_domains: $('#oidc-allowed-domains').val().split(',').map(function (domain) {
                return domain.trim();
            }).filter(Boolean),
            auto_create_users: $('#oidc-auto-create').is(':checked'),
            auto_link_by_email: $('#oidc-auto-link').is(':checked'),
            require_verified_email: $('#oidc-require-verified').is(':checked'),
            sync_group_memberships: $('#oidc-sync-groups').is(':checked'),
            remove_missing_group_memberships: $('#oidc-remove-groups').is(':checked'),
            default_group_id: Number($('#oidc-default-group').val()),
            default_role_id: Number($('#oidc-default-role').val())
        };
    }

    function resetProviderForm() {
        $('#oidc-provider-form')[0].reset();
        $('#oidc-provider-id').val('');
        $('#oidc-callback-url').val('');
        $('#oidc-client-secret').attr('placeholder', translations.client_secret);
        $('#oidc-scope').val('openid email profile');
        $('#oidc-subject-claim').val('sub');
        $('#oidc-email-claim').val('email');
        $('#oidc-username-claim').val('preferred_username');
        $('#oidc-groups-claim').val('groups');
        $('#oidc-enabled, #oidc-auto-link, #oidc-require-verified, #oidc-sync-groups').prop('checked', true);
        $('#oidc-auto-create, #oidc-remove-groups').prop('checked', false);
        $('#oidc-default-role').val('4');
        refreshProviderWidgets();
        if (providerDialog) {
            providerDialog.dialog('option', 'title', translations.new_provider);
        }
    }

    function refreshProviderWidgets() {
        $('#oidc-provider-dialog input[type="checkbox"]').each(function () {
            if ($.fn.checkboxradio && $(this).checkboxradio('instance')) {
                $(this).checkboxradio('refresh');
            }
        });
        $('#oidc-provider-dialog select').each(function () {
            if ($.fn.selectmenu && $(this).selectmenu('instance')) {
                $(this).selectmenu('refresh');
            }
        });
    }

    function resizeProviderDialog() {
        if (!providerDialog) return;
        providerDialog.dialog('option', {
            width: Math.max(280, Math.min(960, window.innerWidth - 30)),
            maxHeight: Math.max(280, window.innerHeight - 40)
        });
    }

    function openNewProviderDialog() {
        resetProviderForm();
        resizeProviderDialog();
        providerDialog.dialog('open');
    }

    function editProvider(provider) {
        $('#oidc-provider-id').val(provider.id);
        $('#oidc-slug').val(provider.slug);
        $('#oidc-label').val(provider.label);
        $('#oidc-callback-url').val(provider.callback_url || '');
        $('#oidc-client-id').val(provider.client_id || '');
        $('#oidc-client-secret').val('').attr(
            'placeholder',
            provider.client_secret_configured ? translations.configured_keep : translations.client_secret
        );
        $('#oidc-metadata-url').val(provider.metadata_url || '');
        $('#oidc-issuer').val(provider.issuer || '');
        $('#oidc-authorization-endpoint').val(provider.authorization_endpoint || '');
        $('#oidc-token-endpoint').val(provider.token_endpoint || '');
        $('#oidc-userinfo-endpoint').val(provider.userinfo_endpoint || '');
        $('#oidc-jwks-uri').val(provider.jwks_uri || '');
        $('#oidc-scope').val(provider.scope || 'openid email profile');
        $('#oidc-subject-claim').val(provider.subject_claim || 'sub');
        $('#oidc-email-claim').val(provider.email_claim || 'email');
        $('#oidc-username-claim').val(provider.username_claim || 'preferred_username');
        $('#oidc-groups-claim').val(provider.groups_claim || 'groups');
        $('#oidc-allowed-domains').val((provider.allowed_domains || []).join(', '));
        $('#oidc-default-group').val(String(provider.default_group_id));
        $('#oidc-default-role').val(String(provider.default_role_id));
        $('#oidc-enabled').prop('checked', provider.enabled);
        $('#oidc-auto-create').prop('checked', provider.auto_create_users);
        $('#oidc-auto-link').prop('checked', provider.auto_link_by_email);
        $('#oidc-require-verified').prop('checked', provider.require_verified_email);
        $('#oidc-sync-groups').prop('checked', provider.sync_group_memberships);
        $('#oidc-remove-groups').prop('checked', provider.remove_missing_group_memberships);
        refreshProviderWidgets();
        providerDialog.dialog('option', 'title', translate('edit_provider', {provider: provider.label}));
        resizeProviderDialog();
        providerDialog.dialog('open');
    }

    function renderProviders() {
        const body = $('#oidc-provider-list').empty();

        providers.forEach(function (provider) {
            const row = $('<tr>');
            $('<td>').addClass('padding10').append(
                $('<button type="button">').addClass('oidc-provider-name').text(provider.label).on('click', function () {
                    openMappingsDialog(provider);
                }),
                $('<div>').addClass('oidc-muted').text(provider.slug)
            ).appendTo(row);
            $('<td>').text(provider.enabled ? translations.enabled : translations.disabled).appendTo(row);
            $('<td>').text(provider.client_id || '').appendTo(row);
			$('<td>').addClass('admin-actions-cell').append(
				actionMenu([
					{icon: 'map', title: translations.mappings_action, handler: function () { openMappingsDialog(provider); }},
					{icon: 'edit', title: translations.edit_action, handler: function () { editProvider(provider); }}
				], $('#oidc-provider-table'))
            ).appendTo(row);
            body.append(row);
        });

        if (!providers.length) {
			body.append($('<tr>').append($('<td colspan="4">').addClass('padding10').text(translations.no_providers)));
        }
        refreshIcons(body);
    }

    function loadProviders() {
        $.ajax({
            url: '/admin/oidc/providers',
            type: 'GET',
            success: function (data) {
                providers = data;
                renderProviders();
            },
			error: function (xhr) { RoxywiUI.error(responseError(xhr)); },
			suppressGlobalError: true
        });
    }

    function mappingPayload() {
        return {
            external_group: $('#oidc-external-group').val().trim(),
            group_id: Number($('#oidc-mapping-group').val()),
            role_id: Number($('#oidc-mapping-role').val()),
            priority: Number($('#oidc-mapping-priority').val()),
            active: $('#oidc-mapping-active').is(':checked')
        };
    }

    function resetMappingForm() {
        $('#oidc-mapping-id').val('');
        $('#oidc-external-group').val('');
        $('#oidc-mapping-priority').val('100');
        $('#oidc-mapping-active').prop('checked', true);
        refreshMappingWidgets();
        if (mappingDialog) {
            mappingDialog.dialog('option', 'title', translations.new_mapping);
        }
    }

    function refreshMappingWidgets() {
        $('#oidc-mapping-dialog input[type="checkbox"]').each(function () {
            if ($.fn.checkboxradio && $(this).checkboxradio('instance')) {
                $(this).checkboxradio('refresh');
            }
        });
        $('#oidc-mapping-dialog select').each(function () {
            if ($.fn.selectmenu && $(this).selectmenu('instance')) {
                $(this).selectmenu('refresh');
            }
        });
    }

    function resizeMappingDialog() {
        if (!mappingDialog) return;
        mappingDialog.dialog('option', {
            width: Math.max(280, Math.min(720, window.innerWidth - 30)),
            maxHeight: Math.max(280, window.innerHeight - 40)
        });
    }

    function resizeMappingsDialog() {
        if (!mappingsDialog) return;
        mappingsDialog.dialog('option', {
            width: Math.max(280, Math.min(900, window.innerWidth - 30)),
            maxHeight: Math.max(280, window.innerHeight - 40)
        });
    }

    function closeMappingsDialogForEditor() {
        restoreMappingsDialog = mappingsDialog.dialog('isOpen');
        if (restoreMappingsDialog) {
            preserveMappingsStateOnClose = true;
            mappingsDialog.dialog('close');
        }
    }

    function closeMappingEditor() {
        resetMappingForm();
        if (restoreMappingsDialog && selectedMappingProvider) {
            restoreMappingsDialog = false;
            resizeMappingsDialog();
            mappingsDialog.dialog('open');
        }
    }

    function openMappingsDialog(provider) {
        restoreMappingsDialog = false;
        selectedMappingProvider = provider;
        const providerName = provider.label || provider.slug;
        $('#oidc-mappings-context').text(translate('provider_prefix', {provider: providerName}));
        $('#oidc-mapping-list').html(
            $('<tr>').append($('<td colspan="7">').addClass('padding10').text(translations.loading_mappings))
        );
        mappingsDialog.dialog('option', 'title', translate('mappings_for', {provider: providerName}));
        resizeMappingsDialog();
        mappingsDialog.dialog('open');
        loadMappings(provider.id);
    }

    function openNewMappingDialog() {
        if (!selectedMappingProvider) {
            toastr.error(translations.select_provider);
            return;
        }
        resetMappingForm();
        closeMappingsDialogForEditor();
        mappingDialog.dialog(
            'option',
            'title',
            translate('new_mapping_for', {
                provider: selectedMappingProvider.label || selectedMappingProvider.slug
            })
        );
        resizeMappingDialog();
        mappingDialog.dialog('open');
    }

    function editMapping(mapping) {
        $('#oidc-mapping-id').val(mapping.id);
        $('#oidc-external-group').val(mapping.external_group);
        $('#oidc-mapping-group').val(String(mapping.group_id));
        $('#oidc-mapping-role').val(String(mapping.role_id));
        $('#oidc-mapping-priority').val(mapping.priority);
        $('#oidc-mapping-active').prop('checked', mapping.active);
        refreshMappingWidgets();
        closeMappingsDialogForEditor();
        mappingDialog.dialog('option', 'title', translate('edit_mapping', {group: mapping.external_group}));
        resizeMappingDialog();
        mappingDialog.dialog('open');
    }

    function renderMappings() {
        const body = $('#oidc-mapping-list').empty();
        mappings.forEach(function (mapping) {
            const row = $('<tr>');
            $('<td>').addClass('padding10').text(mapping.external_group).appendTo(row);
            $('<td>').text(mapping.group_name || mapping.group_id).appendTo(row);
            $('<td>').text(mapping.role_name || mapping.role_id).appendTo(row);
            $('<td>').text(mapping.active ? translations.active : translations.disabled).appendTo(row);
            $('<td>').text(mapping.priority).appendTo(row);
			$('<td>').addClass('admin-actions-cell').append(
				actionMenu([
					{icon: 'edit', title: translations.edit_action, handler: function () { editMapping(mapping); }},
					{icon: 'delete', title: translations.delete_action, danger: true, handler: function () {
					const remove = function () {
						$.ajax({
							url: '/admin/oidc/mappings/' + mapping.id,
							type: 'DELETE',
							success: function () {
								toastr.success(translations.mapping_deleted);
								loadMappings(selectedMappingProvider && selectedMappingProvider.id);
							},
							error: function (xhr) { RoxywiUI.error(responseError(xhr), {action: translations.delete_action}); },
							suppressGlobalError: true
						});
					};
					if (window.RoxywiUI) {
						RoxywiUI.confirm({
							title: translations.delete_action,
							message: translate('delete_mapping_confirm', {group: mapping.external_group}),
							confirmText: translations.delete_action
						}).then(function (confirmed) { if (confirmed) remove(); });
					}
				}}
				], $('#oidc-mapping-list').closest('table'))
            ).appendTo(row);
            body.append(row);
        });
        if (!mappings.length) {
			body.append($('<tr>').append($('<td colspan="6">').addClass('padding10').text(translations.no_mappings)));
        }
        refreshIcons(body);
    }

    function loadMappings(providerId) {
        resetMappingForm();
        if (!providerId) {
            mappings = [];
            renderMappings();
            return;
        }
        $.ajax({
            url: '/admin/oidc/providers/' + providerId + '/mappings',
            type: 'GET',
            success: function (data) {
                if (!selectedMappingProvider || selectedMappingProvider.id !== providerId) return;
                mappings = data;
                renderMappings();
            },
            error: function (xhr) {
                if (selectedMappingProvider && selectedMappingProvider.id === providerId) {
					RoxywiUI.error(responseError(xhr));
                }
			},
			suppressGlobalError: true
        });
    }

    $(function () {
        providerDialog = $('#oidc-provider-dialog').dialog({
            autoOpen: false,
            modal: true,
            width: 960,
            maxHeight: Math.max(280, window.innerHeight - 40),
            classes: {
                'ui-dialog': 'oidc-provider-modal'
            },
            buttons: [{
                text: translations.save_provider,
                click: function () {
                    const form = document.getElementById('oidc-provider-form');
                    if (form.reportValidity()) {
                        $(form).trigger('submit');
                    }
                }
            }, {
                text: translations.cancel,
                click: function () {
                    $(this).dialog('close');
                }
            }],
            close: resetProviderForm
        });
        mappingsDialog = $('#oidc-mappings-dialog').dialog({
            autoOpen: false,
            modal: true,
            width: 900,
            maxHeight: Math.max(280, window.innerHeight - 40),
            classes: {
                'ui-dialog': 'oidc-mappings-modal'
            },
            buttons: [{
                text: translations.close,
                click: function () {
                    $(this).dialog('close');
                }
            }],
            close: function () {
                if (preserveMappingsStateOnClose) {
                    preserveMappingsStateOnClose = false;
                    return;
                }
                restoreMappingsDialog = false;
                selectedMappingProvider = null;
                mappings = [];
                renderMappings();
            }
        });
        mappingDialog = $('#oidc-mapping-dialog').dialog({
            autoOpen: false,
            modal: true,
            width: 720,
            maxHeight: Math.max(280, window.innerHeight - 40),
            classes: {
                'ui-dialog': 'oidc-mapping-modal'
            },
            buttons: [{
                text: translations.save_mapping,
                click: function () {
                    const form = document.getElementById('oidc-mapping-form');
                    if (form.reportValidity()) {
                        $(form).trigger('submit');
                    }
                }
            }, {
                text: translations.cancel,
                click: function () {
                    $(this).dialog('close');
                }
            }],
            close: closeMappingEditor
        });
        resetProviderForm();
        resetMappingForm();
        loadProviders();

        $('#oidc-new-provider').on('click', openNewProviderDialog);
        $('#oidc-new-mapping').on('click', openNewMappingDialog);
        $('#oidc-reload-mappings').on('click', function () {
            if (selectedMappingProvider) {
                loadMappings(selectedMappingProvider.id);
            }
        });

        $('#oidc-provider-form').on('submit', function (event) {
            event.preventDefault();
            const providerId = Number($('#oidc-provider-id').val());
            $.ajax({
                url: providerId ? '/admin/oidc/providers/' + providerId : '/admin/oidc/providers',
                type: providerId ? 'PUT' : 'POST',
                contentType: 'application/json; charset=utf-8',
                data: JSON.stringify(providerPayload()),
                success: function (provider) {
                    toastr.success(translations.provider_saved);
                    providerDialog.dialog('close');
                    loadProviders();
                },
				error: function (xhr) { RoxywiUI.error(responseError(xhr), {action: translations.save}); },
				suppressGlobalError: true
            });
        });

        $('#oidc-mapping-form').on('submit', function (event) {
            event.preventDefault();
            const mappingId = Number($('#oidc-mapping-id').val());
            const providerId = selectedMappingProvider && selectedMappingProvider.id;
            if (!providerId) {
                toastr.error(translations.select_provider);
                return;
            }
            $.ajax({
                url: mappingId ? '/admin/oidc/mappings/' + mappingId : '/admin/oidc/providers/' + providerId + '/mappings',
                type: mappingId ? 'PUT' : 'POST',
                contentType: 'application/json; charset=utf-8',
                data: JSON.stringify(mappingPayload()),
                success: function () {
                    toastr.success(translations.mapping_saved);
                    mappingDialog.dialog('close');
                    loadMappings(providerId);
                },
				error: function (xhr) { RoxywiUI.error(responseError(xhr), {action: translations.save}); },
				suppressGlobalError: true
            });
        });

        $(window).on('resize.oidcDialogs', function () {
            resizeProviderDialog();
            resizeMappingsDialog();
            resizeMappingDialog();
        });
    });
})();
