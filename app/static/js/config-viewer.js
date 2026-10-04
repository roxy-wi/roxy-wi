(function (window, $) {
    'use strict';
    let request = null;
    let generation = 0;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function cancel() {
        generation += 1;
        if (request) request.abort();
        request = null;
    }

    function messages() {
        const node = document.getElementById('config-viewer-messages');
        return node ? JSON.parse(node.textContent) : {};
    }

    function load(payload, historyUrl) {
        cancel();
        const current = generation;
        const host = document.getElementById('ajax');
        if (!host) { $(function () { load(payload, historyUrl); }); return; }
        const i18n = messages();
        const loading = element('p', 'rw-loading-state', i18n.loading);
        loading.setAttribute('role', 'status');
        host.replaceChildren(loading);
        function failed(message) {
            if (current !== generation) return;
            const panel = element('div', 'rw-error-state');
            panel.setAttribute('role', 'alert');
            panel.append(element('p', '', message || i18n.failed));
            const retry = element('button', 'rw-button rw-button-secondary', i18n.retry);
            retry.type = 'button';
            retry.addEventListener('click', () => load(payload, historyUrl));
            panel.append(retry);
            host.replaceChildren(panel);
        }
        request = $.ajax({
            url: '/config/' + encodeURIComponent(payload.service) + '/show',
            type: 'POST', contentType: 'application/json; charset=utf-8',
            data: JSON.stringify(payload), suppressGlobalError: true,
            success: function (response) {
                if (current !== generation) return;
                if (response.status === 'failed' || typeof response.data !== 'string') {
                    failed(response.error);
                    return;
                }
                $(host).html(response.data);
                mount(host.querySelector('.config-viewer'));
                if (historyUrl) window.history.pushState(null, '', historyUrl);
            },
            error: function (xhr, status) {
                if (status !== 'abort') failed(xhr.responseJSON && xhr.responseJSON.error);
            },
            complete: function () { if (current === generation) request = null; }
        });
    }

    function mount(root) {
        if (!root || root.dataset.mounted) return;
        root.dataset.mounted = 'true';
        const config = JSON.parse(root.querySelector('.cv-document').textContent);
        const i18n = JSON.parse(root.querySelector('.cv-i18n').textContent);
        const lines = config.text.split('\n');
        if (lines[lines.length - 1] === '') lines.pop();
        const displayLines = lines.map(line => line.replace(/\r$/, ''));
        const lowerLines = displayLines.map(line => line.toLowerCase());
        const sectionsHost = root.querySelector('.cv-sections');
        const rawHost = root.querySelector('.cv-raw');
        const search = root.querySelector('.cv-search');
        const status = root.querySelector('.cv-status');
        const empty = root.querySelector('.cv-empty');
        const expand = root.querySelector('.cv-expand');
        const previous = root.querySelector('.cv-prev');
        const next = root.querySelector('.cv-next');
        let mode = 'sections';
        let query = '';
        let matches = [];
        let currentMatch = -1;
        let searchTimer;
        const openSections = new Set(config.sections.length ? [config.sections[0].id] : []);
        const rows = [];
        const matchesByLine = new Map();

        function updateStatus() {
            const progress = matches.length ? `${currentMatch + 1}/${matches.length}` : '0';
            status.textContent = query ? `${progress} ${i18n.matches}` : `${config.line_count} ${i18n.lines} · ${config.sections.length} ${i18n.sections.toLowerCase()}`;
            previous.disabled = next.disabled = matches.length === 0;
            const visible = rows.filter(row => !row.details.hidden);
            expand.textContent = visible.length && visible.every(row => row.details.open) ? i18n.collapse : i18n.expand;
            expand.disabled = visible.length === 0;
        }

        function renderCode(start, end) {
            const code = element('div', 'cv-code');
            const fragment = document.createDocumentFragment();
            for (let index = start - 1; index < end; index += 1) {
                const row = element('div', 'cv-line');
                row.dataset.line = String(index + 1);
                const number = element('span', 'cv-number', index + 1);
                number.setAttribute('aria-hidden', 'true');
                const text = element('span', 'cv-text');
                const source = displayLines[index];
                const hits = matchesByLine.get(index) || [];
                if (hits.length) {
                    let offset = 0;
                    hits.forEach(hit => {
                        text.append(document.createTextNode(source.slice(offset, hit.offset)));
                        const mark = element('mark', hit.index === currentMatch ? 'cv-current' : '', source.slice(hit.offset, hit.offset + query.length));
                        mark.dataset.match = hit.index;
                        text.append(mark);
                        offset = hit.offset + query.length;
                    });
                    text.append(document.createTextNode(source.slice(offset)));
                } else if (source.trimStart().startsWith('#')) {
                    text.append(element('span', 'cv-comment', source));
                } else {
                    const token = source.match(/^(\s*)([^\s]+)(.*)$/);
                    if (token) text.append(document.createTextNode(token[1]), element('span', 'cv-keyword', token[2]), document.createTextNode(token[3]));
                    else text.textContent = source || ' ';
                }
                row.append(number, text);
                fragment.append(row);
            }
            code.append(fragment);
            return code;
        }

        async function copy(text) {
            try {
                await navigator.clipboard.writeText(text);
                status.textContent = i18n.copied;
            } catch (error) {
                // Permissions and insecure origins can disable the Clipboard API.
                status.textContent = i18n.copy_failed;
            }
        }

        function openEditor(section, event) {
            if (section.editor !== 'form-or-text' || typeof window.openSection !== 'function') return;
            event.preventDefault();
            window.openSection(section.title, {
                server: config.source.server, filePath: config.source.path,
                mainFile: config.source.main_file, textUrl: section.edit_url, errorMessage: i18n.failed
            });
        }

        config.sections.forEach(section => {
            const details = element('details', 'cv-section');
            details.id = 'cv-' + section.id;
            const summary = element('summary');
            summary.append(element('span', 'cv-title', section.title || i18n.preamble), element('span', 'cv-range', `${section.start_line}–${section.end_line}`));
            const body = element('div', 'cv-section-body');
            const actions = element('div', 'cv-section-actions');
            const copyButton = element('button', 'cv-button', i18n.copy_section);
            copyButton.type = 'button';
            copyButton.addEventListener('click', () => {
                const originalLines = config.text.match(/[^\n]*\n|[^\n]+$/g) || [];
                copy(originalLines.slice(section.start_line - 1, section.end_line).join(''));
            });
            actions.append(copyButton);
            (section.open_urls || []).forEach(target => {
                const link = element('a', 'cv-button', `${i18n.open} :${target.port}`);
                link.href = target.url;
                link.target = '_blank';
                link.rel = 'noopener';
                actions.append(link);
            });
            if (section.stats_url) {
                const stats = element('a', 'cv-button', i18n.stats);
                stats.href = section.stats_url;
                stats.target = '_blank';
                stats.rel = 'noopener';
                actions.append(stats);
            }
            if (section.edit_url) {
                const edit = element('a', 'cv-button cv-edit-section', i18n.edit_section);
                edit.href = section.edit_url;
                edit.addEventListener('click', event => openEditor(section, event));
                actions.append(edit);
            }
            body.append(actions);
            details.append(summary, body);
            const row = {section, details, body, code: null};
            rows.push(row);
            details.open = openSections.has(section.id);
            details.addEventListener('toggle', () => {
                if (details.open && !row.code) {
                    row.code = renderCode(section.start_line, section.end_line);
                    body.append(row.code);
                }
                if (!query) {
                    if (details.open) openSections.add(section.id);
                    else openSections.delete(section.id);
                }
                updateStatus();
            });
            sectionsHost.append(details);
        });

        function render() {
            sectionsHost.hidden = mode !== 'sections';
            rawHost.hidden = mode !== 'raw';
            expand.hidden = mode !== 'sections';
            root.querySelectorAll('[data-cv-mode]').forEach(button => {
                button.setAttribute('aria-pressed', String(button.dataset.cvMode === mode));
            });
            rows.forEach(row => {
                const {section, details} = row;
                const hit = matches.some(match => match.line + 1 >= section.start_line && match.line + 1 <= section.end_line);
                details.hidden = Boolean(query) && !hit;
                details.open = query ? hit : openSections.has(section.id);
                if (row.code) row.code.remove();
                row.code = null;
                if (mode === 'sections' && details.open && !details.hidden) {
                    row.code = renderCode(section.start_line, section.end_line);
                    row.body.append(row.code);
                }
            });
            rawHost.replaceChildren();
            if (mode === 'raw') rawHost.append(renderCode(1, config.line_count));
            empty.hidden = config.line_count > 0 && (!query || matches.length > 0);
            empty.textContent = config.line_count ? i18n.empty : i18n.empty_file;
            updateStatus();
        }

        function searchNow() {
            query = search.value.toLowerCase();
            matches = [];
            matchesByLine.clear();
            if (query) lowerLines.forEach((line, index) => {
                let offset = line.indexOf(query);
                while (offset !== -1) {
                    const hit = {line: index, offset, index: matches.length};
                    matches.push(hit);
                    if (!matchesByLine.has(index)) matchesByLine.set(index, []);
                    matchesByLine.get(index).push(hit);
                    offset = line.indexOf(query, offset + query.length);
                }
            });
            currentMatch = matches.length ? 0 : -1;
            render();
        }

        function navigateMatch(direction) {
            window.clearTimeout(searchTimer);
            if (query !== search.value.toLowerCase()) searchNow();
            if (!matches.length) return;
            currentMatch = (currentMatch + direction + matches.length) % matches.length;
            const match = matches[currentMatch];
            const row = rows.find(item => match.line + 1 >= item.section.start_line && match.line + 1 <= item.section.end_line);
            if (mode === 'sections' && row) {
                row.details.open = true;
                if (!row.code) { row.code = renderCode(row.section.start_line, row.section.end_line); row.body.append(row.code); }
            }
            root.querySelectorAll('.cv-current').forEach(mark => mark.classList.remove('cv-current'));
            const host = mode === 'raw' ? rawHost : sectionsHost;
            const target = host.querySelector(`[data-match="${currentMatch}"]`);
            if (target) {
                target.classList.add('cv-current');
                target.scrollIntoView({block: 'center', inline: 'nearest'});
            }
            updateStatus();
        }

        search.addEventListener('input', () => {
            window.clearTimeout(searchTimer);
            searchTimer = window.setTimeout(() => { if (root.isConnected) searchNow(); }, 120);
        });
        search.addEventListener('keydown', event => {
            if (event.key === 'Enter') { event.preventDefault(); navigateMatch(event.shiftKey ? -1 : 1); }
            if (event.key === 'Escape') { search.value = ''; searchNow(); }
        });
        previous.addEventListener('click', () => navigateMatch(-1));
        next.addEventListener('click', () => navigateMatch(1));
        root.addEventListener('keydown', event => {
            if (event.ctrlKey || event.metaKey || event.altKey || event.repeat ||
                event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
            const controls = {
                r: '[data-cv-mode="raw"]', a: '[data-cv-mode="sections"]',
                x: '.cv-expand', e: '#edit_link'
            };
            const selector = controls[event.key.toLowerCase()];
            const control = selector && root.querySelector(selector);
            if (control && !control.hidden && !control.disabled) {
                event.preventDefault();
                control.click();
            }
        });
        root.querySelectorAll('[data-cv-mode]').forEach(button => button.addEventListener('click', () => { mode = button.dataset.cvMode; render(); }));
        root.querySelector('.cv-wrap').addEventListener('change', event => root.querySelector('.cv-content').classList.toggle('cv-wrapped', event.target.checked));
        root.querySelector('.cv-copy').addEventListener('click', () => copy(config.text));
        expand.addEventListener('click', () => {
            const visible = rows.filter(row => !row.details.hidden);
            const shouldOpen = !visible.every(row => row.details.open);
            visible.forEach(row => {
                row.details.open = shouldOpen;
                if (!query) {
                    if (shouldOpen) openSections.add(row.section.id);
                    else openSections.delete(row.section.id);
                }
            });
            updateStatus();
        });
        const nginxEdit = root.querySelector('[data-nginx-edit]');
        if (nginxEdit && typeof window.openNginxSection === 'function') nginxEdit.addEventListener('click', event => {
            event.preventDefault();
            window.openNginxSection(nginxEdit.dataset.nginxEdit);
        });
        render();
        const selected = config.sections.find(section => section.title === root.dataset.editSection && section.edit_url);
        if (selected) {
            const row = rows.find(item => item.section.id === selected.id);
            row.details.open = true;
            if (selected.editor === 'form-or-text') openEditor(selected, {preventDefault() {}});
            else window.location.assign(selected.edit_url);
        }
    }

    window.ConfigViewer = {mount, load, cancel};
})(window, window.jQuery);
