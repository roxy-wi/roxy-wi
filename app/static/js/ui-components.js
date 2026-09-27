(function (window, $) {
	'use strict';

	function text(name, fallback) {
		const value = $('#translate').attr('data-' + name);
		return value || fallback;
	}

	function parse(value) {
		if (typeof window.parseRoxywiResponse === 'function') {
			return window.parseRoxywiResponse(value);
		}
		let raw = value;
		if (value && typeof value === 'object') {
			raw = value.error || value.message || JSON.stringify(value);
		}
		raw = String(raw || text('something_wrong', 'Something went wrong'));
		return {summary: raw, raw: raw, errors: [], warnings: []};
	}

	function ensureNotificationDialog() {
		let dialog = $('#rw-notification-dialog');
		if (!dialog.length) {
			dialog = $('<div id="rw-notification-dialog" class="rw-notification-dialog" aria-live="assertive"></div>').appendTo(document.body);
		}
		return dialog;
	}

	function showError(value, options) {
		options = options || {};
		const parsed = parse(value);
		const server = options.server || (value && value.server);
		const action = options.action || (value && value.action);
		const dialog = ensureNotificationDialog().empty();
		$('<p class="rw-error-state"></p>').text(options.operation || action || options.title || text('operation_failed', 'Operation failed')).appendTo(dialog);
		const details = $('<dl class="rw-notification-details"></dl>').appendTo(dialog);
		if (options.operation || action) {
			details.append($('<dt></dt>').text(text('what-failed', 'What failed')))
				.append($('<dd></dd>').text(options.operation || action));
		}
		if (server) {
			details.append($('<dt></dt>').text(text('server', 'Server'))).append($('<dd></dd>').text(server));
		}
		details.append($('<dt></dt>').text(text('reason', 'Reason'))).append($('<dd></dd>').text(parsed.summary));
		if (options.nextAction) {
			details.append($('<dt></dt>').text(text('next-action', 'What to do next')))
				.append($('<dd></dd>').text(options.nextAction));
		}
		if (parsed.raw && parsed.raw !== parsed.summary) {
			const details = $('<details></details>').appendTo(dialog);
			details.append($('<summary></summary>').text(text('raw', 'Raw output')));
			details.append($('<pre class="rw-notification-raw"></pre>').text(parsed.raw));
		}
		const buttons = [];
		if (typeof options.retry === 'function') {
			buttons.push({
				text: options.retryText || text('retry-action', 'Retry'),
				click: function () { $(this).dialog('close'); options.retry(); }
			});
		}
		if (options.logsUrl) {
			buttons.push({
				text: options.logsText || text('open-logs', 'Open logs'),
				click: function () { window.location.href = options.logsUrl; }
			});
		}
		buttons.push({text: text('close', 'Close'), click: function () { $(this).dialog('close'); }});
		dialog.dialog({
			modal: true,
			width: Math.min(720, Math.max(320, window.innerWidth - 32)),
			maxHeight: Math.max(360, window.innerHeight - 32),
			title: options.title || text('operation_failed', 'Operation failed'),
			buttons: buttons,
			classes: {'ui-dialog': 'rw-dialog-responsive'}
		});
	}

	function showToastError(value, options) {
		options = options || {};
		const parsed = parse(value);
		const content = $('<div class="rw-toast-error"></div>');
		const operation = options.operation || options.action;
		if (operation) {
			content.append($('<b></b>').text(operation)).append('<br>');
		}
		content.append($('<span></span>').text(parsed.summary));
		toastr.error(content.html(), options.title || text('operation_failed', 'Operation failed'));
	}

	function confirmAction(options) {
		options = options || {};
		return new Promise(function (resolve) {
			const dialog = $('<div></div>').text(options.message || text('are_you_sure', 'Are you sure?')).appendTo(document.body);
			let resolved = false;
			dialog.dialog({
				modal: true,
				width: Math.min(520, Math.max(300, window.innerWidth - 32)),
				title: options.title || text('confirm', 'Confirm'),
				classes: {'ui-dialog': 'rw-dialog-responsive'},
				buttons: [{
					text: options.confirmText || text('apply', 'Apply'),
					click: function () { resolved = true; $(this).dialog('close'); resolve(true); }
				}, {
					text: options.cancelText || text('cancel', 'Cancel'),
					click: function () { resolved = true; $(this).dialog('close'); resolve(false); }
				}],
				close: function () { if (!resolved) resolve(false); dialog.remove(); }
			});
		});
	}

	function enhanceTable(table) {
		const $table = $(table);
		if ($table.data('rw-enhanced')) return;
		$table.data('rw-enhanced', true).addClass('rw-table-responsive');
		const headings = $table.find('thead th, tr.overviewHead:first th').map(function () { return $(this).text().trim(); }).get();
		if (!$table.parent().hasClass('rw-table-shell')) $table.wrap('<div class="rw-table-shell"></div>');
		const shell = $table.parent();
		const pageSize = Number($table.data('page-size')) || 0;
		let currentPage = 1;
		let query = '';
		let sortColumn = -1;
		let sortDirection = 1;
		let internalMutation = false;
		const storageKey = 'roxywi-table-filter:' + window.location.pathname + ':' + ($table.attr('id') || 'table');

		function rows() { return $table.find('tbody tr, > tr:not(.overviewHead)'); }
		function labelRows() {
			rows().each(function () {
				$(this).children('td').each(function (index) { $(this).attr('data-label', headings[index] || ''); });
			});
		}
		function render() {
			let visibleRows = rows().get().filter(function (row) {
				return !query || $(row).text().toLocaleLowerCase().indexOf(query) !== -1;
			});
			if (sortColumn >= 0) {
				visibleRows.sort(function (left, right) {
					return $(left).children().eq(sortColumn).text().trim().localeCompare(
						$(right).children().eq(sortColumn).text().trim(), undefined, {numeric: true}
					) * sortDirection;
				});
				internalMutation = true;
				visibleRows.forEach(function (row) { $table.children('tbody').append(row); });
				window.setTimeout(function () { internalMutation = false; }, 0);
			}
			const maxPage = pageSize ? Math.max(1, Math.ceil(visibleRows.length / pageSize)) : 1;
			currentPage = Math.min(currentPage, maxPage);
			rows().hide();
			visibleRows.forEach(function (row, index) {
				if (!pageSize || (index >= (currentPage - 1) * pageSize && index < currentPage * pageSize)) $(row).show();
			});
			shell.siblings('.rw-table-empty').prop('hidden', visibleRows.length !== 0);
			const pager = shell.siblings('.rw-table-pager');
			pager.prop('hidden', !pageSize || maxPage <= 1);
			pager.find('.rw-page-current').text(currentPage + ' / ' + maxPage);
			pager.find('[data-page="prev"]').prop('disabled', currentPage <= 1);
			pager.find('[data-page="next"]').prop('disabled', currentPage >= maxPage);
		}

		labelRows();
		$table.find('thead th').each(function (index) {
			if ($(this).attr('data-sortable') === 'false') return;
			$(this).attr({tabindex: '0', role: 'button', 'aria-sort': 'none'}).on('click keydown', function (event) {
				if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
				event.preventDefault();
				sortDirection = sortColumn === index ? -sortDirection : 1;
				sortColumn = index;
				$table.find('thead th[role="button"]').attr('aria-sort', 'none');
				$(this).attr('aria-sort', sortDirection === 1 ? 'ascending' : 'descending');
				render();
			});
		});
		if ($table.data('searchable')) {
			const toolbar = $('<div class="rw-table-toolbar rw-table-search-toolbar"></div>').insertBefore(shell);
			const search = $('<input type="search">').attr('placeholder', text('search', 'Search')).appendTo(toolbar);
			try { search.val(localStorage.getItem(storageKey) || ''); } catch (error) { /* Optional. */ }
			query = search.val().trim().toLocaleLowerCase();
			search.on('input', function () {
				query = search.val().trim().toLocaleLowerCase(); currentPage = 1;
				try { localStorage.setItem(storageKey, search.val()); } catch (error) { /* Optional. */ }
				render();
			});
		}
		$('<div class="rw-empty-state rw-table-empty" hidden></div>').text(text('no-results', 'No results')).insertAfter(shell);
		if (pageSize) {
			const pager = $('<div class="rw-table-pager" hidden></div>').insertAfter(shell);
			pager.append('<button type="button" class="rw-icon-button" data-page="prev" aria-label="Previous">‹</button>');
			pager.append('<span class="rw-page-current"></span>');
			pager.append('<button type="button" class="rw-icon-button" data-page="next" aria-label="Next">›</button>');
			pager.on('click', 'button', function () { currentPage += $(this).data('page') === 'next' ? 1 : -1; render(); });
		}
		new MutationObserver(function () {
			labelRows();
			if (!internalMutation) render();
		}).observe($table.find('tbody').get(0) || table, {childList: true});
		render();
	}

	window.RoxywiUI = {
		parseResponse: parse,
		error: showError,
		toastError: showToastError,
		confirm: confirmAction,
		enhanceTable: enhanceTable
	};

	function closeAdminActionMenus() {
		$('.admin-actions-menu').prop('hidden', true).removeAttr('style');
		$('.admin-actions-toggle').attr('aria-expanded', 'false');
	}

	function positionAdminActionMenu(button, menu) {
		menu.prop('hidden', false).css({top: 0, left: 0, visibility: 'hidden'});
		const buttonRect = button[0].getBoundingClientRect();
		const menuWidth = menu.outerWidth();
		const menuHeight = menu.outerHeight();
		const viewportPadding = 8;
		let left = buttonRect.right - menuWidth;
		let top = buttonRect.bottom + 5;

		left = Math.max(viewportPadding, Math.min(left, window.innerWidth - menuWidth - viewportPadding));
		if (top + menuHeight > window.innerHeight - viewportPadding) {
			top = Math.max(viewportPadding, buttonRect.top - menuHeight - 5);
		}
		menu.css({top: top + 'px', left: left + 'px', visibility: 'visible'});
	}

	$(document).on('click', '.admin-actions-toggle', function (event) {
		event.preventDefault();
		event.stopPropagation();
		const button = $(this);
		const menu = button.siblings('.admin-actions-menu');
		const shouldOpen = menu.prop('hidden');
		closeAdminActionMenus();
		if (shouldOpen) {
			positionAdminActionMenu(button, menu);
			button.attr('aria-expanded', 'true');
		}
	});

	$(document).on('click', '.admin-actions-menu .admin-action-item', function () {
		closeAdminActionMenus();
	});

	$(document).on('click', function (event) {
		if (!$(event.target).closest('.admin-actions').length) closeAdminActionMenus();
	});

	$(document).on('keydown', function (event) {
		if (event.key === 'Escape') closeAdminActionMenus();
	});

	$(window).on('resize', closeAdminActionMenus);
	document.addEventListener('scroll', closeAdminActionMenus, true);

	$(function () {
		$('table[data-ux-table]').each(function () { enhanceTable(this); });
	});
})(window, window.jQuery);
