$(function () {
    const root = $('#change-center');
    const tableBody = $('#change-center-table tbody');
    const i18n = $('#change-center-i18n').data();
    const currentUserId = Number(root.data('user-id'));
    const currentRole = Number(root.data('role'));
    let changesById = {};
    let actionPoll = null;
    let activeRequests = 0;
    let openDetailsId = null;
    let detailTimelinePoll = null;
    let iconRefreshScheduled = false;
    let allChanges = [];
    let changesLoaded = false;
    const filterStorageKey = 'roxywi-change-center-filters:v1';

    function textCell(value) {
        return $('<td>').text(value == null ? '' : value);
    }

    function statusText(status) {
        const statusKey = status.replace(/_([a-z])/g, function (_match, letter) { return letter.toUpperCase(); });
        return i18n[statusKey] || status.replaceAll('_', ' ');
    }

    function statusLabel(status) {
        return $('<span>').addClass('rw-status-badge change-status change-status-' + status).text(statusText(status));
    }

    function driftLabel(status) {
        const value = status || 'unknown';
        const key = 'drift' + value.replace(/(^|_)([a-z])/g, function (_match, _prefix, letter) { return letter.toUpperCase(); });
        return $('<span>').addClass('change-drift-status change-drift-status-' + value)
            .text(i18n[key] || value.replaceAll('_', ' '));
    }

    function driftValue(change) {
        return change.status === 'deployed' ? (change.drift_status || 'unknown') : 'not_applicable';
    }

    function refreshSelectmenu(select) {
        if ($.fn.selectmenu && select.selectmenu('instance')) {
            select.selectmenu('refresh');
        }
    }

    function actionButton(icon, title, action, changeId, menuItem, visibleLabel) {
        const button = $('<button type="button" class="ui-button ui-widget ui-corner-all">')
            .addClass('change-action-' + action)
            .attr('title', title)
            .attr('aria-label', title)
            .append($('<span aria-hidden="true">').addClass('fas ' + icon))
            .on('click', function (event) {
                event.stopPropagation();
                closeActionMenus();
                runAction(changeId, action);
            });
        if (menuItem) {
            button.addClass('change-action-menu-item').attr('role', 'menuitem').append($('<span>').text(title));
        } else if (visibleLabel) {
            button.addClass('change-action-labeled').append($('<span>').text(title));
        }
        return button;
    }

    function closeActionMenus(except) {
        $('.change-actions-menu').each(function () {
            if (except && this === except) return;
            $(this).prop('hidden', true).siblings('.change-action-more').attr('aria-expanded', 'false');
        });
    }

    function appendSecondaryAction(menu, icon, title, action, changeId) {
        menu.append(actionButton(icon, title, action, changeId, true));
    }

    function refreshActionIcons() {
        if (window.FontAwesome && window.FontAwesome.dom && window.FontAwesome.dom.i2svg) {
            window.FontAwesome.dom.i2svg({node: tableBody.get(0)});
            const webhookDialog = document.getElementById('change-webhooks-dialog');
            if (webhookDialog) {
                window.FontAwesome.dom.i2svg({node: webhookDialog});
            }
			const rollout = document.getElementById('change-details-rollout');
			if (rollout) {
				window.FontAwesome.dom.i2svg({node: rollout});
			}
			const timeline = document.getElementById('change-details-timeline');
			if (timeline) {
				window.FontAwesome.dom.i2svg({node: timeline});
			}
			return;
        }
		if (!iconRefreshScheduled) {
			iconRefreshScheduled = true;
			window.addEventListener('load', function () {
				iconRefreshScheduled = false;
				refreshActionIcons();
			}, {once: true});
		}
    }

    function renderActions(change) {
        const actions = $('<td>').addClass('change-actions');
        const primary = $('<div class="change-actions-primary">');
        const menuId = 'change-actions-menu-' + change.id;
        const menu = $('<div class="change-actions-menu" role="menu" hidden>').attr('id', menuId);
        primary.append(actionButton('fa-eye', i18n.details, 'details', change.id));
        if (['draft', 'validation_failed'].includes(change.status)) {
            primary.append(actionButton('fa-check', i18n.validate, 'validate', change.id));
        }
        if (change.status === 'pending_approval' && currentRole <= 2 && change.user_id !== currentUserId) {
            primary.append(actionButton('fa-user-check', i18n.approve, 'approve', change.id));
        }
        if (['validated', 'approved', 'auto_rolled_back', 'auto_rollback_failed', 'rollback_failed'].includes(change.status)) {
            primary.append(actionButton('fa-rocket', i18n.deploy, 'deploy', change.id));
        }
        if (['validated', 'approved', 'schedule_missed'].includes(change.status)) {
            appendSecondaryAction(menu, 'fa-calendar-alt', i18n.schedule, 'schedule', change.id);
        }
        if (change.status === 'scheduled') {
            appendSecondaryAction(menu, 'fa-calendar-times', i18n.cancelSchedule, 'cancel-schedule', change.id);
        }
        if (change.status === 'deploying') {
            primary.append(actionButton('fa-pause', i18n.pause, 'pause', change.id));
        }
        if (['pause_requested', 'paused', 'deployment_interrupted'].includes(change.status)) {
            primary.append(actionButton('fa-play', i18n.resume, 'resume', change.id, false, true));
        }
        if (change.status === 'awaiting_promotion') {
            primary.append(actionButton('fa-forward', i18n.promote, 'promote', change.id));
            appendSecondaryAction(menu, 'fa-pause', i18n.pause, 'pause', change.id);
        }
        if (['deployed', 'rollback_failed', 'auto_rollback_failed', 'deployment_interrupted'].includes(change.status)) {
            appendSecondaryAction(menu, 'fa-undo', i18n.rollback, 'rollback', change.id);
        }
        if (change.status === 'deployed') {
            appendSecondaryAction(menu, 'fa-search-location', i18n.checkDrift, 'drift', change.id);
        }
        appendSecondaryAction(menu, 'fa-file-export', i18n.exportReport, 'report', change.id);
        if (['draft', 'validation_failed', 'validated', 'pending_approval', 'approved'].includes(change.status)) {
            appendSecondaryAction(menu, 'fa-times', i18n.cancel, 'cancel', change.id);
        }
        if (change.recoverable) {
            primary.append(actionButton('fa-unlock-alt', i18n.recover, 'recover', change.id));
        }
        if (menu.children().length) {
            const more = $('<button type="button" class="ui-button ui-widget ui-corner-all change-action-more">')
                .attr({'title': i18n.moreActions, 'aria-label': i18n.moreActions, 'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-controls': menuId})
                .append('<span class="fas fa-ellipsis-v" aria-hidden="true"></span>')
                .on('click', function (event) {
                    event.stopPropagation();
                    const willOpen = menu.prop('hidden');
                    closeActionMenus(menu.get(0));
                    menu.prop('hidden', !willOpen);
                    $(this).attr('aria-expanded', String(willOpen));
                    if (willOpen) menu.find('button:first').trigger('focus');
                });
            primary.append(more).append(menu);
        }
        actions.append(primary);
        return actions;
    }

    function render(changes) {
        tableBody.empty();
        changes.forEach(function (change) {
            const row = $('<tr>');
            row.append(textCell(change.id));
            row.append(textCell(change.title));
            row.append(textCell(change.service));
            row.append(textCell((change.server_name || '') + (change.server_ip ? ' (' + change.server_ip + ')' : '')));
            const status = $('<td>').append(statusLabel(change.status));
            if (change.status === 'scheduled' && change.scheduled_at) {
                status.append($('<small class="change-scheduled-at">').text(new Date(change.scheduled_at).toLocaleString()));
            }
            row.append(status);
            row.append($('<td>').append(driftLabel(driftValue(change))));
            row.append(textCell(change.created_by));
            row.append(textCell(change.created_at ? new Date(change.created_at).toLocaleString() : ''));
            row.append(renderActions(change));
            tableBody.append(row);
        });
        refreshActionIcons();
        if (openDetailsId && changesById[openDetailsId] && $('#change-details-dialog').dialog('isOpen')) {
            renderDetailsContent(changesById[openDetailsId]);
        }
        $('#change-center-table').prop('hidden', changes.length === 0);
    }

    function readFilters() {
        try {
            return JSON.parse(window.localStorage.getItem(filterStorageKey) || '{}');
        } catch (error) {
            return {};
        }
    }

    function saveFilters() {
        const filters = {
            search: $('#change-list-search').val(),
            service: $('#change-list-service').val(),
            status: $('#change-list-status').val(),
            drift: $('#change-list-drift').val()
        };
        try { window.localStorage.setItem(filterStorageKey, JSON.stringify(filters)); } catch (error) { /* Optional. */ }
    }

    function fillFilter(select, values, label) {
        const current = select.val() || select.data('restore-value') || '';
        if (current && !values.includes(current)) values.unshift(current);
        select.find('option:not(:first)').remove();
        values.forEach(function (value) {
            select.append($('<option>').val(value).text(label(value)));
        });
        select.val(values.includes(current) ? current : '');
        select.removeData('restore-value');
        refreshSelectmenu(select);
    }

    function updateFilterOptions() {
        fillFilter($('#change-list-service'), Array.from(new Set(allChanges.map(function (change) { return change.service; }).filter(Boolean))).sort(), function (value) { return value.toUpperCase(); });
        fillFilter($('#change-list-status'), Array.from(new Set(allChanges.map(function (change) { return change.status; }).filter(Boolean))).sort(), statusText);
        fillFilter($('#change-list-drift'), Array.from(new Set(allChanges.map(driftValue))).sort(), function (value) { return driftLabel(value).text(); });
    }

    function applyFilters() {
        const search = $('#change-list-search').val().trim().toLocaleLowerCase();
        const service = $('#change-list-service').val();
        const status = $('#change-list-status').val();
        const drift = $('#change-list-drift').val();
        const filtered = allChanges.filter(function (change) {
            const haystack = [change.id, change.title, change.service, change.server_name, change.server_ip, change.created_by]
                .filter(function (value) { return value != null; }).join(' ').toLocaleLowerCase();
            return (!search || haystack.includes(search)) && (!service || change.service === service) &&
                (!status || change.status === status) && (!drift || driftValue(change) === drift);
        });
        render(filtered);
        $('#change-center-empty').toggle(allChanges.length === 0);
        $('#change-center-no-results').toggle(allChanges.length > 0 && filtered.length === 0);
        $('#change-list-count').text((i18n.showingChanges || '{shown} / {total}')
            .replace('{shown}', filtered.length).replace('{total}', allChanges.length));
        saveFilters();
    }

    function setListState(state) {
        const stateBox = $('#change-center-list-state');
        const loading = state === 'loading';
        const failed = state === 'error';
        $('#change-center-table').attr('aria-busy', String(loading));
        stateBox.toggle(loading || failed).toggleClass('change-list-state-error', failed);
        stateBox.find('.fa-circle-notch').toggle(loading);
        stateBox.find('.change-list-state-message').text(failed ? i18n.loadFailed : i18n.loading);
        $('#change-list-retry').prop('hidden', !failed);
    }

    function loadChanges() {
        if (!changesLoaded) {
            setListState('loading');
        } else {
            $('#change-center-table').attr('aria-busy', 'true');
        }
        return $.getJSON('/changes/api')
            .done(function (response) {
                allChanges = response.data || [];
                changesLoaded = true;
                changesById = {};
                allChanges.forEach(function (change) { changesById[change.id] = change; });
                updateFilterOptions();
                applyFilters();
                setListState('ready');
            })
            .fail(function () { setListState('error'); });
    }

    function formatDuration(seconds) {
        const value = Number(seconds || 0);
        if (value < 60) return Math.round(value) + 's';
        if (value < 3600) return Math.round(value / 60) + 'm';
        return (value / 3600).toFixed(1) + 'h';
    }

    function loadStatistics() {
        $.getJSON('/changes/api/statistics', {days: 30}).done(function (response) {
            const data = response.data || {};
            $('#change-stat-deployments').text(data.deployments == null ? '—' : data.deployments);
            $('#change-stat-success-rate').text(data.success_rate == null ? '—' : data.success_rate + '%');
            $('#change-stat-duration').text(formatDuration(data.average_duration_seconds));
            $('#change-stat-drift').text(data.drifted_targets == null ? '—' : data.drifted_targets);
        });
    }

    function renderDiff(diff) {
        const container = $('#change-details-diff').empty();
        if (!diff) {
            container.text('—');
            return;
        }
        diff.replace(/\r\n/g, '\n').split('\n').forEach(function (content) {
            let lineType = 'context';
            if (content.startsWith('+++') || content.startsWith('---')) {
                lineType = 'header';
            } else if (content.startsWith('@@')) {
                lineType = 'hunk';
            } else if (content.startsWith('+')) {
                lineType = 'added';
            } else if (content.startsWith('-')) {
                lineType = 'removed';
            }
            container.append(
                $('<span>')
                    .addClass('change-diff-line change-diff-' + lineType)
                    .text(content || '\u00a0')
            );
        });
    }

    function targetOutput(target) {
        const output = target.rollback_output || target.deployment_output || target.validation_output;
        return normalizeRoxywiResponse(output) || '—';
    }

    function targetActionButton(icon, title, action, changeId, targetId) {
        return $('<button type="button" class="ui-button ui-widget ui-corner-all">')
            .addClass('change-target-action-' + action)
            .attr('title', title)
            .attr('aria-label', title)
            .append($('<span aria-hidden="true">').addClass('fas ' + icon))
            .on('click', function () { runTargetAction(changeId, targetId, action); });
    }

    function renderTargetActions(change, target) {
        const actions = $('<div class="change-target-actions">');
        const controllable = ['paused', 'awaiting_promotion', 'deployment_interrupted', 'auto_rolled_back', 'auto_rollback_failed', 'rollback_failed'];
        if (target.excluded) {
            if (controllable.includes(change.status) || ['draft', 'validation_failed'].includes(change.status)) {
                actions.append(targetActionButton('fa-plus-circle', i18n.includeNode, 'include', change.id, target.id));
            }
            return actions;
        }
        if (controllable.includes(change.status) && target.status !== 'deployed') {
            actions.append(targetActionButton('fa-redo', i18n.retryNode, 'retry', change.id, target.id));
        }
        if ((controllable.includes(change.status) || change.status === 'deployed') && ['deployed', 'deployment_failed', 'deployment_interrupted', 'rollback_failed'].includes(target.status)) {
            actions.append(targetActionButton('fa-undo', i18n.rollbackNode, 'rollback', change.id, target.id));
        }
        if (target.role === 'slave' && (controllable.includes(change.status) || ['draft', 'validation_failed'].includes(change.status)) && !['deployed', 'deploying', 'rolling_back'].includes(target.status)) {
            actions.append(targetActionButton('fa-minus-circle', i18n.excludeNode, 'exclude', change.id, target.id));
        }
        return actions;
    }

    function renderRollout(change) {
        const targets = change.targets || [];
        const body = $('#change-details-rollout tbody').empty();
        targets.forEach(function (target) {
            const roleKey = 'role' + target.role.charAt(0).toUpperCase() + target.role.slice(1);
            const row = $('<tr>');
            row.append(textCell(target.server_name + ' (' + target.server_ip + ')'));
            row.append(textCell(i18n[roleKey] || target.role));
            row.append(textCell(target.excluded ? '—' : target.batch + 1));
            row.append(textCell(target.is_canary ? i18n.canary : '—'));
            row.append($('<td>').append(statusLabel(target.status)));
            row.append($('<td>').append($('<pre>').text(normalizeRoxywiResponse(target.health_output) || '—')));
            row.append($('<td>').append($('<pre>').text(targetOutput(target))));
            row.append($('<td>').append(renderTargetActions(change, target)));
            body.append(row);
        });
        if (targets.length === 0) {
            body.append($('<tr>').append($('<td colspan="8">').text('—')));
        }
        refreshActionIcons();
    }

    function renderDetailsContent(change) {
        const executionMode = change.execution_mode || 'rolling';
        const executionModeKey = 'executionMode' + executionMode.charAt(0).toUpperCase() + executionMode.slice(1);
        const healthMode = change.health_check_mode || 'full';
        const healthModeKey = 'healthMode' + healthMode.charAt(0).toUpperCase() + healthMode.slice(1);
        $('#change-details-summary').empty()
            .append($('<p>').text('#' + change.id + ' — ' + change.title))
            .append($('<p>').text(change.service + ' / ' + (change.server_name || change.server_id) + ' / ' + change.remote_path))
            .append($('<p>').text(i18n.executionMode + ': ' + (i18n[executionModeKey] || executionMode)))
            .append($('<p>').text(i18n.batchSize + ': ' + change.effective_batch_size + ' / ' + i18n.maxParallel + ': ' + change.max_parallel))
            .append($('<p>').text(i18n.healthCheck + ': ' + (i18n[healthModeKey] || healthMode) + (change.manual_promotion ? ' / ' + i18n.manualPromotion : '')))
            .append(change.scheduled_at ? $('<p>').text(i18n.schedule + ': ' + new Date(change.scheduled_at).toLocaleString()) : $())
            .append($('<p>').append(driftLabel(driftValue(change))))
            .append($('<p>').text(change.description || ''));
        renderRollout(change);
        renderDiff(change.diff);
        const driftEligible = change.status === 'deployed';
        $('#change-details-drift-section').toggle(driftEligible);
        if (driftEligible) renderDiffInto($('#change-details-drift'), change.drift_diff);
        $('#change-details-validation').text(normalizeRoxywiResponse(change.validation_output) || '—');
        $('#change-details-deployment').text(normalizeRoxywiResponse(change.deployment_output) || '—');
        $('#change-details-rollback').text(normalizeRoxywiResponse(change.rollback_output) || '—');
        loadTimeline(change.id);
    }

    function renderDiffInto(container, diff) {
        container.empty();
        if (!diff) {
            container.text('—');
            return;
        }
        diff.replace(/\r\n/g, '\n').split('\n').forEach(function (content) {
            let lineType = 'context';
            if (content.startsWith('+++') || content.startsWith('---')) lineType = 'header';
            else if (content.startsWith('@@')) lineType = 'hunk';
            else if (content.startsWith('+')) lineType = 'added';
            else if (content.startsWith('-')) lineType = 'removed';
            container.append($('<span>').addClass('change-diff-line change-diff-' + lineType).text(content || '\u00a0'));
        });
    }

    function timelineIcon(eventType) {
        if ((eventType || '').includes('failed')) return 'fa-exclamation-circle';
        if ((eventType || '').includes('succeeded') || (eventType || '').includes('deployed')) return 'fa-check-circle';
        if ((eventType || '').includes('rollback')) return 'fa-undo';
        if ((eventType || '').includes('drift')) return 'fa-search-location';
        if ((eventType || '').includes('schedule')) return 'fa-calendar-alt';
        if ((eventType || '').includes('pause')) return 'fa-pause-circle';
        return 'fa-circle';
    }

    function relativeTime(value) {
        if (!value) return '';
        if (!window.Intl || !window.Intl.RelativeTimeFormat) return new Date(value).toLocaleString();
        const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
        const formatter = new Intl.RelativeTimeFormat(undefined, {numeric: 'auto'});
        if (Math.abs(seconds) < 60) return formatter.format(seconds, 'second');
        const minutes = Math.round(seconds / 60);
        if (Math.abs(minutes) < 60) return formatter.format(minutes, 'minute');
        const hours = Math.round(minutes / 60);
        if (Math.abs(hours) < 24) return formatter.format(hours, 'hour');
        return formatter.format(Math.round(hours / 24), 'day');
    }

    function renderTimeline(events) {
        const timeline = $('#change-details-timeline');
        const nearBottom = timeline.scrollTop() + timeline.innerHeight() >= timeline.get(0).scrollHeight - 32;
        timeline.empty();
        (events || []).slice().reverse().forEach(function (event) {
            const exactTime = event.created_at ? new Date(event.created_at).toLocaleString() : '';
            const item = $('<div class="change-timeline-item">')
                .addClass('change-timeline-' + String(event.event_type || 'event').replace(/[^a-z0-9_-]/gi, '-'));
            item.append($('<span class="change-timeline-icon" aria-hidden="true">').append($('<span>').addClass('fas ' + timelineIcon(event.event_type))));
            const content = $('<div class="change-timeline-content">');
            content.append($('<strong>').text(event.target_name ? event.target_name + ': ' + event.message : event.message));
            content.append($('<span>').text([event.actor_name, event.event_type].filter(Boolean).join(' · ')));
            content.append($('<time>').attr('datetime', event.created_at || '').attr('title', exactTime).text(relativeTime(event.created_at)));
            item.append(content);
            timeline.append(item);
        });
        if (!(events || []).length) timeline.text('—');
        if (nearBottom || timeline.scrollTop() === 0) timeline.scrollTop(timeline.get(0).scrollHeight);
        refreshActionIcons();
    }

    function loadTimeline(changeId) {
        if (openDetailsId !== changeId) return;
        $.getJSON('/changes/api/' + changeId + '/events', {limit: 500})
            .done(function (response) { renderTimeline(response.data || []); });
    }

    function showDetails(change) {
        openDetailsId = change.id;
        renderDetailsContent(change);
        $('#change-details-dialog').dialog({
            modal: true,
            width: '80%',
            maxHeight: 800,
            close: function () {
                openDetailsId = null;
                window.clearInterval(detailTimelinePoll);
                detailTimelinePoll = null;
            }
        }).dialog('open');
        window.clearInterval(detailTimelinePoll);
        detailTimelinePoll = window.setInterval(function () { loadTimeline(change.id); }, 2000);
    }

    function confirmAction(action, message, callback) {
        const titles = {
            deploy: i18n.deploy,
            rollback: i18n.rollback,
            cancel: i18n.cancel,
            recover: i18n.recover,
            pause: i18n.pause,
            resume: i18n.resume,
            promote: i18n.promote,
            cancelSchedule: i18n.cancelSchedule,
            drift: i18n.checkDrift,
            retry: i18n.retryNode,
            rollbackNode: i18n.rollbackNode,
            exclude: i18n.excludeNode,
            include: i18n.includeNode
            , deleteWebhook: i18n.delete
        };
        const dialog = $('#change-confirm-dialog');
        $('#change-confirm-message').text(message);
        dialog.dialog({
            autoOpen: false,
            modal: true,
            resizable: false,
            width: 450,
            title: titles[action],
            buttons: [
                {
                    text: i18n.confirm,
                    class: 'change-confirm-button change-confirm-' + action,
                    click: function () {
                        dialog.dialog('close');
                        callback();
                    }
                },
                {
                    text: i18n.cancel,
                    click: function () { dialog.dialog('close'); }
                }
            ]
        }).dialog('open');
    }

    function executeAction(changeId, action) {
        const endpoint = action === 'cancel-schedule' ? 'schedule/cancel' : action;
        $.ajax({
            url: '/changes/api/' + changeId + '/' + endpoint,
            method: 'POST',
            dataType: 'json',
            beforeSend: function () {
                toastr.clear();
                activeRequests += 1;
                if (!actionPoll) {
                    actionPoll = window.setInterval(loadChanges, 1500);
                }
            },
            success: function (response) {
                const messages = {
                    validate: i18n.validated,
                    approve: i18n.approved,
                    deploy: i18n.deployed,
                    rollback: i18n.rolledBack,
                    cancel: i18n.cancelled,
                    recover: i18n.recovered
                };
                const responseStatus = response.data && response.data.status;
                const statusKey = responseStatus ? responseStatus.replace(/_([a-z])/g, function (_match, letter) { return letter.toUpperCase(); }) : '';
                toastr.success(i18n[statusKey] || messages[action] || i18n.operationSuccess);
                loadChanges();
            },
            error: function () {
                loadChanges();
            },
            complete: function () {
                activeRequests = Math.max(0, activeRequests - 1);
                if (!activeRequests) {
                    window.clearInterval(actionPoll);
                    actionPoll = null;
                }
            }
        });
    }

    function runAction(changeId, action) {
        if (action === 'details') {
            showDetails(changesById[changeId]);
            return;
        }
        if (action === 'report') {
            window.location.assign('/changes/api/' + changeId + '/report?format=csv');
            return;
        }
        if (action === 'schedule') {
            openScheduleDialog(changeId);
            return;
        }
        const confirmations = {
            deploy: i18n.confirmDeploy,
            rollback: i18n.confirmRollback,
            cancel: i18n.confirmCancel,
            recover: i18n.confirmRecover,
            pause: i18n.confirmPause,
            resume: i18n.confirmResume,
            promote: i18n.confirmPromote
            , 'cancel-schedule': i18n.confirmCancelSchedule
            , drift: i18n.confirmDrift
        };
        if (confirmations[action]) {
            confirmAction(action, confirmations[action], function () {
                executeAction(changeId, action);
            });
            return;
        }
        executeAction(changeId, action);
    }

    function openScheduleDialog(changeId) {
        const dialog = $('#change-schedule-dialog');
        const start = new Date(Date.now() + 5 * 60000);
        start.setSeconds(0, 0);
        $('#change-scheduled-at').val(new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16));
        $('#change-window-end').val('');
        $('#change-scheduled-at, #change-window-end').attr('min', new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16));
        $('#change-schedule-timezone').text(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' + (-new Date().getTimezoneOffset() / 60));
        dialog.dialog({
            modal: true,
            width: Math.min(480, window.innerWidth - 30),
            buttons: [
                {text: i18n.save, class: 'change-primary-button', click: function () {
                    const scheduledValue = $('#change-scheduled-at').val();
                    if (!scheduledValue) return;
                    const windowValue = $('#change-window-end').val();
                    if (new Date(scheduledValue).getTime() <= Date.now() || (windowValue && new Date(windowValue) <= new Date(scheduledValue))) {
                        toastr.warning(i18n.invalidSchedule);
                        return;
                    }
                    $.ajax({
                        url: '/changes/api/' + changeId + '/schedule',
                        method: 'POST',
                        contentType: 'application/json; charset=UTF-8',
                        data: JSON.stringify({
                            scheduled_at: new Date(scheduledValue).toISOString(),
                            maintenance_window_end: windowValue ? new Date(windowValue).toISOString() : null
                        }),
                        success: function () {
                            dialog.dialog('close');
                            toastr.success(i18n.scheduleSaved);
                            loadChanges();
                        }
                    });
                }},
                {text: i18n.cancel, click: function () { dialog.dialog('close'); }}
            ]
        }).dialog('open');
    }

    function executeTargetAction(changeId, targetId, action) {
        $.ajax({
            url: '/changes/api/' + changeId + '/targets/' + targetId + '/' + action,
            method: 'POST',
            contentType: 'application/json; charset=UTF-8',
            dataType: 'json',
            data: action === 'exclude' ? JSON.stringify({reason: null}) : undefined,
            beforeSend: function () {
                toastr.clear();
                activeRequests += 1;
                if (!actionPoll) {
                    actionPoll = window.setInterval(loadChanges, 1500);
                }
            },
            success: function () {
                toastr.success(i18n.operationSuccess);
                loadChanges();
            },
            error: function () { loadChanges(); },
            complete: function () {
                activeRequests = Math.max(0, activeRequests - 1);
                if (!activeRequests) {
                    window.clearInterval(actionPoll);
                    actionPoll = null;
                }
            }
        });
    }

    function runTargetAction(changeId, targetId, action) {
        const confirmations = {
            retry: i18n.confirmRetryNode,
            rollback: i18n.confirmRollbackNode,
            exclude: i18n.confirmExcludeNode,
            include: i18n.confirmIncludeNode
        };
        const dialogAction = action === 'rollback' ? 'rollbackNode' : action;
        confirmAction(dialogAction, confirmations[action], function () {
            executeTargetAction(changeId, targetId, action);
        });
    }

    function auditQuery() {
        const query = {limit: 500};
        const search = $('#change-audit-search').val();
        const service = $('#change-audit-service').val();
        const dateFrom = $('#change-audit-from').val();
        const dateTo = $('#change-audit-to').val();
        if (search) query.q = search;
        if (service) query.service = service;
        if (dateFrom) query.date_from = new Date(dateFrom + 'T00:00:00').toISOString();
        if (dateTo) query.date_to = new Date(dateTo + 'T23:59:59').toISOString();
        return query;
    }

    function renderTableMessage(body, colspan, message, retry) {
        body.empty();
        const content = $('<div class="change-table-message">').append($('<span>').text(message));
        if (retry) {
            const button = $('<button type="button" class="ui-button ui-widget ui-corner-all">')
                .append('<span class="fas fa-redo" aria-hidden="true"></span>')
                .append(document.createTextNode(' ' + i18n.retry))
                .on('click', retry);
            content.append(button);
        }
        body.append($('<tr>').append($('<td>').attr('colspan', colspan).append(content)));
    }

    function loadAudit() {
        const body = $('#change-audit-dialog tbody');
        renderTableMessage(body, 6, i18n.loading);
        $.getJSON('/changes/api/audit', auditQuery()).done(function (response) {
            body.empty();
            (response.data || []).forEach(function (event) {
                body.append($('<tr>')
                    .append(textCell(event.created_at ? new Date(event.created_at).toLocaleString() : ''))
                    .append(textCell(event.change_id))
                    .append(textCell(event.service))
                    .append($('<td>').append(statusLabel(event.status || 'draft')))
                    .append(textCell(event.actor_name || '—'))
                    .append(textCell((event.target_name ? event.target_name + ': ' : '') + event.message)));
            });
            if (!(response.data || []).length) {
                body.append($('<tr>').append($('<td colspan="6">').text('—')));
            }
        }).fail(function () { renderTableMessage(body, 6, i18n.loadFailed, loadAudit); });
    }

    $('#change-open-audit').on('click', function () {
        loadAudit();
        $('#change-audit-dialog').dialog({
            modal: true,
            width: Math.min(1100, window.innerWidth - 30),
            maxHeight: Math.max(420, window.innerHeight - 80),
            buttons: [{text: i18n.close, click: function () { $(this).dialog('close'); }}]
        }).dialog('open');
    });
    $('#change-audit-refresh').on('click', loadAudit);
    let auditSearchTimer = null;
    $('#change-audit-search').on('input', function () {
        window.clearTimeout(auditSearchTimer);
        auditSearchTimer = window.setTimeout(loadAudit, 300);
    });
    $('#change-audit-service').on('change selectmenuchange', loadAudit);
    $('#change-audit-from, #change-audit-to').on('change', loadAudit);

    function webhookAction(icon, title, callback) {
        return $('<button type="button" class="ui-button ui-widget ui-corner-all">')
            .attr({title: title, 'aria-label': title})
            .append($('<span aria-hidden="true">').addClass('fas ' + icon))
            .on('click', callback);
    }

    const webhookEvents = $('#change-webhook-events');
    if (webhookEvents.length && $.fn.selectmenu && webhookEvents.selectmenu('instance')) {
        webhookEvents.selectmenu('destroy');
    }
    if (webhookEvents.length && $.fn.select2) {
        webhookEvents.select2({
            width: '100%',
            dropdownParent: $('#change-webhooks-dialog'),
            closeOnSelect: false
        });
    }

    function resetWebhookForm(webhook) {
        $('#change-webhook-id').val(webhook ? webhook.id : '');
        $('#change-webhook-name').val(webhook ? webhook.name : '');
        $('#change-webhook-url').val(webhook ? webhook.url : '');
        $('#change-webhook-secret').val('').attr('placeholder', webhook && webhook.secret_configured ? '••••••••' : '');
        webhookEvents
            .val(webhook ? webhook.events : ['deployment.succeeded', 'deployment.failed', 'drift.detected'])
            .trigger('change.select2');
        $('#change-webhook-enabled').prop('checked', webhook ? webhook.enabled : true);
        $('#change-webhook-verify-tls').prop('checked', webhook ? webhook.verify_tls : true);
        $('#change-webhook-form').prop('hidden', false);
    }

    function loadWebhooks() {
        if (!$('#change-webhooks-dialog').length) return;
        const body = $('#change-webhooks-dialog tbody');
        renderTableMessage(body, 4, i18n.loading);
        $.getJSON('/changes/api/webhooks').done(function (response) {
            body.empty();
            (response.data || []).forEach(function (webhook) {
                const actions = $('<div class="change-webhook-actions">')
                    .append(webhookAction('fa-edit', i18n.edit, function () { resetWebhookForm(webhook); }))
                    .append(webhookAction('fa-paper-plane', i18n.test, function (event) {
                        const button = $(event.currentTarget).prop('disabled', true);
                        $.post('/changes/api/webhooks/' + webhook.id + '/test').done(function () {
                            toastr.success(i18n.webhookTestQueued);
                        }).always(function () { button.prop('disabled', false); });
                    }))
                    .append(webhookAction('fa-trash', i18n.delete, function () {
                        confirmAction('deleteWebhook', i18n.confirmDeleteWebhook.replace('{name}', function () { return webhook.name; }), function () {
                            $.ajax({url: '/changes/api/webhooks/' + webhook.id, method: 'DELETE'})
                                .done(function () { loadWebhooks(); });
                        });
                    }));
                body.append($('<tr>')
                    .append(textCell(webhook.name))
                    .append(textCell(webhook.url))
                    .append($('<td>').append(
                        $('<span>')
                            .addClass('change-status change-status-' + (webhook.enabled ? 'deployed' : 'cancelled'))
                            .text(webhook.enabled ? i18n.enabled : i18n.disabled)
                    ))
                    .append($('<td>').append(actions)));
            });
            if (!(response.data || []).length) body.append($('<tr>').append($('<td colspan="4">').text('—')));
            refreshActionIcons();
        }).fail(function () { renderTableMessage(body, 4, i18n.loadFailed, loadWebhooks); });
    }

    $('#change-open-webhooks').on('click', function () {
        $('#change-webhook-form').prop('hidden', true);
        loadWebhooks();
        $('#change-webhooks-dialog').dialog({
            modal: true,
            width: Math.min(900, window.innerWidth - 30),
            maxHeight: Math.max(480, window.innerHeight - 80),
            buttons: [{text: i18n.close, click: function () { $(this).dialog('close'); }}]
        }).dialog('open');
    });
    $('#change-webhook-new').on('click', function () { resetWebhookForm(null); });
    $('#change-webhook-form-cancel').on('click', function () { $('#change-webhook-form').prop('hidden', true); });
    $('#change-webhook-form').on('submit', function (event) {
        event.preventDefault();
        const form = $(this);
        const webhookId = $('#change-webhook-id').val();
        const secret = $('#change-webhook-secret').val();
        const payload = {
            name: $('#change-webhook-name').val().trim(),
            url: $('#change-webhook-url').val().trim(),
            events: $('#change-webhook-events').val() || [],
            enabled: $('#change-webhook-enabled').is(':checked'),
            verify_tls: $('#change-webhook-verify-tls').is(':checked')
        };
        if (secret || !webhookId) payload.secret = secret || null;
        $.ajax({
            url: '/changes/api/webhooks' + (webhookId ? '/' + webhookId : ''),
            method: webhookId ? 'PUT' : 'POST',
            contentType: 'application/json; charset=UTF-8',
            data: JSON.stringify(payload),
            beforeSend: function () { form.find('input, select, button').prop('disabled', true); }
        }).done(function () {
            toastr.success(i18n.webhookSaved);
            $('#change-webhook-form').prop('hidden', true);
            loadWebhooks();
        }).always(function () { form.find('input, select, button').prop('disabled', false); });
    });

    const savedFilters = readFilters();
    $('#change-list-search').val(savedFilters.search || '');
    $('#change-list-service').data('restore-value', savedFilters.service || '');
    $('#change-list-status').data('restore-value', savedFilters.status || '');
    $('#change-list-drift').data('restore-value', savedFilters.drift || '');
    $('#change-list-search').on('input', applyFilters);
    $('#change-list-service, #change-list-status, #change-list-drift').on('change selectmenuchange', applyFilters);
    $('#change-list-clear').on('click', function () {
        $('#change-list-search, #change-list-service, #change-list-status, #change-list-drift').val('');
        $('#change-list-service, #change-list-status, #change-list-drift').each(function () {
            refreshSelectmenu($(this));
        });
        applyFilters();
        $('#change-list-search').trigger('focus');
    });
    $('#change-list-retry').on('click', loadChanges);
    $(document).on('click', function () { closeActionMenus(); });
    $(document).on('keydown', function (event) {
        if (event.key === 'Escape') closeActionMenus();
    });

    loadChanges();
    loadStatistics();
    window.setInterval(loadChanges, 60000);
    window.setInterval(loadStatistics, 60000);
});
