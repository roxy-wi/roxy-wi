(function (root) {
    'use strict';
    const MAX_ROWS = 1000;
    const specialSources = new Set(['fail2ban.log', 'roxy-wi.error.log', 'roxy-wi.access.log']);

    function dateParts(date, utc) {
        const part = name => date[(utc ? 'getUTC' : 'get') + name]();
        const pad = n => String(n).padStart(2, '0');
        return {date: `${part('FullYear')}-${pad(part('Month') + 1)}-${pad(part('Date'))}`,
            time: `${pad(part('Hours'))}:${pad(part('Minutes'))}:${pad(part('Seconds'))}`};
    }

    function parseDate(date, time, utc) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}(:\d{2})?$/.test(time)) throw new Error('date');
        if (time.length === 5) time += ':00';
        const value = new Date(`${date}T${time}${utc ? 'Z' : ''}`);
        if (!Number.isFinite(value.getTime())) throw new Error('date');
        const parts = dateParts(value, utc);
        if (parts.date !== date || parts.time !== time) throw new Error('date');
        return value;
    }

    function highlightParts(value, term) {
        value = String(value);
        const parts = [];
        let offset = 0, index;
        if (!term) return [{text: value, match: false}];
        while ((index = value.indexOf(term, offset)) !== -1) {
            if (index > offset) parts.push({text: value.slice(offset, index), match: false});
            parts.push({text: value.slice(index, index + term.length), match: true});
            offset = index + term.length;
        }
        if (offset < value.length) parts.push({text: value.slice(offset), match: false});
        return parts;
    }

    function appendHighlighted(element, value, term) {
        highlightParts(value, term).forEach(part => {
            if (part.match) {
                const mark = document.createElement('mark');
                mark.textContent = part.text;
                element.appendChild(mark);
            } else element.appendChild(document.createTextNode(part.text));
        });
    }

    function parseEntry(entry) {
        let record = null;
        if (entry.text.trimStart().startsWith('{')) {
            try { record = JSON.parse(entry.text); }
            catch (error) { if (!(error instanceof SyntaxError)) throw error; }
        }
        if (!record || typeof record !== 'object' || Array.isArray(record)) record = null;
        const message = record && typeof record.message === 'string' ? record.message : entry.text;
        let level = typeof record?.level === 'string' ? record.level.toUpperCase() : '';
        if (level === 'WARN') level = 'WARNING';
        if (level === 'FATAL') level = 'CRITICAL';
        if (!['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].includes(level)) level = '';
        return {record, message, level, process: typeof record?.process_role === 'string' ? record.process_role : ''};
    }

    function recordFields(record) {
        // Bounded, iterative traversal also handles deeply nested JSON safely.
        const pending = Object.entries(record).reverse().map(([key, value]) => ({key, value, depth: 0}));
        const fields = [];
        while (pending.length && fields.length < 200) {
            const {key, value, depth} = pending.pop();
            if (value !== null && typeof value === 'object') {
                const children = Object.entries(value);
                if (!children.length) fields.push([key, Array.isArray(value) ? '[]' : '{}']);
                else if (depth >= 6) fields.push([key, '…']);
                else children.reverse().forEach(([child, item]) => pending.push({key: `${key}.${child}`, value: item, depth: depth + 1}));
            } else fields.push([key, String(value)]);
        }
        return fields;
    }

    function createLogRow(entry, options) {
        const {record, message, level, process} = parseEntry(entry);
        const make = (tag, className, value) => {
            const node = document.createElement(tag);
            node.className = className;
            if (value !== undefined) appendHighlighted(node, value, options.search);
            return node;
        };
        const row = make('details', 'log-row'), summary = make('summary', 'log-summary');
        row.dataset.timestamp = entry.timestamp;
        const date = new Date(entry.timestamp), parts = dateParts(date, options.utc);
        const time = make('time', 'log-time', (options.showDate ? parts.date + ' ' : '') + parts.time + '.' + String(date.getUTCMilliseconds()).padStart(3, '0'));
        time.dateTime = entry.timestamp;
        time.title = `${parts.date} ${parts.time} (${options.timezone})`;
        const badge = make('span', 'log-level', level === 'WARNING' ? 'WARN' : level || '—');
        badge.dataset.level = level;
        const processNode = make('span', 'log-process', process || options.source || '—');
        const messageNode = make('span', 'log-message', message);
        if (options.search && (entry.text.includes(options.search) || (record && JSON.stringify(record).includes(options.search)))
                && ![time.textContent, badge.textContent, processNode.textContent, message].some(value => value.includes(options.search))) {
            messageNode.appendChild(make('span', 'log-match-details', options.labels.match_fields));
        }
        summary.append(time, badge, processNode, messageNode);
        row.appendChild(summary);
        let built = false;
        row.addEventListener('toggle', () => {
            if (!row.open || built) return;
            built = true;
            const detail = make('div', 'log-detail'), tabs = make('div', 'log-detail-tabs');
            detail.setAttribute('aria-label', options.labels.details);
            const fields = make('dl', 'log-fields'), raw = make('pre', 'log-raw', entry.text);
            if (record) recordFields(record).forEach(([key, value]) => fields.append(make('dt', '', key), make('dd', '', value)));
            const buttons = [];
            const panels = record ? [fields, raw] : [raw];
            const labels = record ? [options.labels.fields, options.labels.raw] : [options.labels.raw];
            panels.forEach((panel, index) => {
                const button = make('button', '', labels[index]);
                button.type = 'button';
                button.setAttribute('aria-pressed', String(index === 0));
                button.addEventListener('click', () => {
                    panels.forEach((item, n) => { item.hidden = n !== index; buttons[n].setAttribute('aria-pressed', String(n === index)); });
                });
                buttons.push(button);
                tabs.appendChild(button);
                panel.hidden = index !== 0;
            });
            detail.append(tabs, ...panels);
            row.appendChild(detail);
        });
        return row;
    }

    // A single outstanding request; a paused/changed query cannot append late responses.
    class Follower {
        constructor(fetch, render, status,
                    schedule = (fn, delay) => setTimeout(fn, delay), cancel = id => clearTimeout(id)) {
            Object.assign(this, {fetch, render, status, schedule, cancel});
            this.generation = 0;
            this.cursor = null;
            this.live = false;
            this.retry = 2000;
        }
        stop() {
            this.live = false;
            this.generation++;
            this.cancel(this.timer);
            if (this.request) this.request.abort();
            this.request = null;
        }
        start(live, reset) {
            this.stop();
            this.live = live;
            if (reset) this.cursor = null;
            this.retry = 2000;
            this.poll();
        }
        poll() {
            const generation = this.generation;
            let delay = 2000;
            const initial = !this.cursor;
            this.request = this.fetch(this.cursor);
            this.request.done(data => {
                if (generation !== this.generation) return;
                this.cursor = data.cursor || null;
                this.retry = 2000;
                delay = data.more ? 250 : 2000;
                this.render(data, initial);
            }).fail((xhr, state) => {
                if (generation !== this.generation || state === 'abort') return;
                const terminal = xhr.status >= 400 && xhr.status < 500;
                if (terminal) this.live = false;
                this.status(terminal ? 'failed' : 'retry', xhr.responseJSON?.error);
                delay = this.retry;
                this.retry = Math.min(30000, this.retry * 2);
            }).always(() => {
                if (generation !== this.generation) return;
                this.request = null;
                if (this.live) this.timer = this.schedule(() => this.poll(), delay);
            });
        }
    }
    root.RoxyLogViewer = {Follower, parseDate, dateParts, highlightParts, parseEntry, recordFields, createLogRow};
    if (!root.document) return;

    $(function () {
        const form = document.getElementById('log-viewer-form');
        if (!form) return;
        const viewer = document.getElementById('log-viewer');
        const text = JSON.parse(viewer.dataset.text);
        const output = document.getElementById('log-output');
        const picker = document.getElementById('log-time-picker');
        const filters = document.getElementById('log-filters');
        const source = document.getElementById('log-source');
        const rowEntries = new WeakMap();
        const internal = form.dataset.internal === 'true';
        let relative = 3600, absolute = null, query = null, endpoint = '', notices = new Set(), fileRequest = null, fileGeneration = 0;
        const value = id => document.getElementById(id)?.value || '';
        const utc = () => value('log-timezone') === 'UTC';
        const timezone = () => utc() ? 'UTC' : Intl.DateTimeFormat().resolvedOptions().timeZone;
        const status = message => $('#log-status').text(message);
        const button = () => {
            $('#log-live').attr('aria-pressed', String(follower.live));
            $('#log-live-label').text(follower.live ? text.pause : 'Live');
            const unavailable = internal ? specialSources.has(source.selectedOptions[0]?.dataset.source)
                : !value('serv') || (form.dataset.waf !== '1' && !value('log_files'));
            $('#log-live').prop('disabled', !relative || unavailable);
            $('#log-live').attr('title', text.live_relative);
            $('#log-zone').text(timezone());
            $('[data-log-relative]').each(function () {this.setAttribute('aria-pressed', String(Number(this.dataset.logRelative) === relative));});
            $('#log-filter-active').prop('hidden', !value('log-exclude') && value('log-limit') === '100');
        };
        function renderRow(entry, open = false) {
            const row = createLogRow(entry, {search: value('log-search'), utc: utc(), timezone: timezone(), labels: text, source: internal ? '' : value('service')});
            rowEntries.set(row, entry);
            row.open = open;
            return row;
        }
        function repaint() {
            Array.from(output.children).forEach(row => row.replaceWith(renderRow(rowEntries.get(row), row.open)));
        }
        const follower = new Follower(cursor => $.ajax({
            url: endpoint, type: 'POST', data: Object.assign({}, query, cursor ? {cursor} : {}),
            dataType: 'json', timeout: 15000, global: false
        }), (data, initial) => {
            if (initial) { output.replaceChildren(); notices = new Set(); }
            const fragment = document.createDocumentFragment();
            data.entries.forEach(entry => {
                fragment.appendChild(renderRow(entry));
            });
            output.appendChild(fragment);
            if (relative) {
                const start = Date.parse(data.start);
                Array.from(output.children).forEach(row => {
                    if (Date.parse(row.dataset.timestamp) < start) row.remove();
                });
            }
            while (output.children.length > MAX_ROWS) output.firstElementChild.remove();
            if (data.limited) notices.add(text.limited);
            if (data.reset) notices.add(text.reset);
            if (data.unparsed) notices.add(text.unparsed + ' ' + data.unparsed);
            $('#log-notice').text(Array.from(notices).join('\n')).prop('hidden', !notices.size);
            $('#log-count').text(`${output.children.length} ${text.rows}`);
            $('#log-empty').prop('hidden', !!output.children.length);
            status(follower.live ? 'Live' : (output.children.length ? text.ready : text.empty));
            if ($('#log-autoscroll').prop('checked') && !output.querySelector('.log-row[open]')) output.scrollTop = output.scrollHeight;
            button();
        }, (state, error) => {status(error || text[state]); button();});

        function parameters() {
            const result = {limit: value('log-limit'), search: value('log-search'), exclude: value('log-exclude'), timezone: timezone()};
            if (relative) result.relative = relative;
            else Object.assign(result, absolute);
            if (internal) {
                result.source = source.selectedOptions[0]?.dataset.source;
                result.process = source.selectedOptions[0]?.dataset.process || '';
                endpoint = '/logs/internal/query';
                if (!result.source) throw new Error(text.select_source);
            } else {
                result.server = value('serv');
                result.file = value('log_files');
                result.waf = form.dataset.waf;
                endpoint = '/logs/query/' + encodeURIComponent(value('service'));
                if (!result.server || (result.waf !== '1' && !result.file)) throw new Error(text.select_source);
            }
            return result;
        }
        function run(live, reset = true) {
            if (!form.checkValidity()) {
                if (!document.getElementById('log-limit').validity.valid) filters.open = true;
                form.reportValidity();
                return;
            }
            try { query = parameters(); } catch (error) {status(error.message); return;}
            if (!internal && live) query.follow = '1';
            status(text.loading);
            follower.start(live, reset);
            button();
        }
        function changed() {
            follower.stop();
            follower.cursor = null;
            status(text.paused);
            button();
        }
        function fillDates() {
            const end = absolute ? new Date(absolute.to) : new Date();
            const start = absolute ? new Date(absolute.from) : new Date(end.getTime() - relative * 1000);
            [['from', start], ['to', end]].forEach(([key, date]) => {
                const parts = dateParts(date, utc());
                $('#log-' + key + '-date').val(parts.date);
                $('#log-' + key + '-time').val(parts.time);
            });
        }
        function absoluteLabel() {
            const label = `${value('log-from-date')} ${value('log-from-time')} → ${value('log-to-date')} ${value('log-to-time')} (${timezone()})`;
            $('#log-time-label').text(label).attr('title', label);
        }
        $('.log-date').datepicker({dateFormat: 'yy-mm-dd', changeMonth: true, changeYear: true});
        fillDates();
        picker.addEventListener('toggle', () => {
            if (picker.open) filters.open = false;
            if (picker.open && relative) fillDates();
            if (!picker.open) $('.log-date').datepicker('hide');
        });
        filters.addEventListener('toggle', () => {if (filters.open) picker.open = false;});
        $('#log-timezone').on('change selectmenuchange', () => {
            fillDates();
            if (absolute) absoluteLabel();
            changed();
            repaint();
        });
        $('[data-log-relative]').on('click', function () {
            relative = Number(this.dataset.logRelative);
            absolute = null;
            $('#log-time-label').text(this.textContent).removeAttr('title');
            picker.open = false;
            fillDates();
            run(follower.live);
        });
        $('#log-apply-time').on('click', () => {
            try {
                const start = parseDate(value('log-from-date'), value('log-from-time'), utc());
                const end = parseDate(value('log-to-date'), value('log-to-time'), utc());
                if (end <= start || end - start > 31 * 86400000) throw new Error('range');
                absolute = {from: start.toISOString(), to: end.toISOString()};
                relative = 0;
                absoluteLabel();
                picker.open = false;
                run(false);
            } catch (_) {status(text.invalid_range);}
        });
        $(form).on('submit', event => {event.preventDefault(); run(false);});
        $('#log-apply-filters').on('click', () => {run(false); if (form.checkValidity()) filters.open = false;});
        $('#log-live').on('click', () => {
            if (follower.live) {follower.stop(); status(text.paused); button();}
            else run(true, !follower.cursor);
        });
        $('#log-search, #log-exclude, #log-limit').on('input', changed);
        $('#log-search').on('input', repaint);
        function clearRows() {output.replaceChildren(); notices.clear(); $('#log-notice, #log-empty').prop('hidden', true); $('#log-count').text('');}
        if (internal) source.addEventListener('change', () => {
            changed();
            clearRows();
            run(false);
        });
        function loadFiles(preferred = '') {
            const select = document.getElementById('log_files');
            if (!select) {if (value('serv')) run(false); return;}
            const generation = ++fileGeneration;
            if (fileRequest) fileRequest.abort();
            select.replaceChildren(new Option(text.select_file, ''));
            select.disabled = true;
            if (!value('serv')) return;
            status(text.loading);
            fileRequest = $.ajax({url: '/logs/' + encodeURIComponent(value('service')) + '/' + encodeURIComponent(value('serv')),
                type: 'POST', dataType: 'json', global: false, timeout: 15000});
            fileRequest.done(data => {
                if (generation !== fileGeneration) return;
                data.files.forEach(file => select.appendChild(new Option(file, file)));
                select.disabled = false;
                if (data.files.includes(preferred)) select.value = preferred;
                else if (data.files.length === 1) select.value = data.files[0];
                status(text.select_source);
                button();
                if (select.value) run(false);
            }).fail((xhr, state) => {
                if (generation !== fileGeneration || state === 'abort') return;
                status(xhr.responseJSON?.error || text.load_files_failed);
            }).always(() => {if (generation === fileGeneration) fileRequest = null;});
        }
        $('#serv').on('change', () => {changed(); clearRows(); form.dataset.file = ''; loadFiles();});
        $('#log_files').on('change', () => {changed(); clearRows(); if (value('log_files')) run(false);});
        $(document).on('keydown', event => {if (event.key === 'Escape') {picker.open = false; filters.open = false;}});
        $(document).on('click', event => {
            if (!picker.contains(event.target) && !event.target.closest('#ui-datepicker-div')) picker.open = false;
            if (!filters.contains(event.target)) filters.open = false;
        });
        window.addEventListener('pagehide', () => {follower.stop(); fileGeneration++; if (fileRequest) fileRequest.abort();});
        document.addEventListener('visibilitychange', () => {
            if (document.hidden && follower.live) {follower.stop(); status(text.paused); button();}
        });
        button();
        if (internal) run(false);
        else loadFiles(form.dataset.file);
    });
})(typeof window !== 'undefined' ? window : globalThis);
