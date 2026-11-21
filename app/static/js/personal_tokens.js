/* Never store a personal credential in localStorage, a cookie, or an URL. */
(() => {
    'use strict';
    const form = document.getElementById('personal-token-form');
    const table = document.querySelector('#personal-token-table tbody');
    const status = document.getElementById('personal-token-status');
    const created = document.getElementById('personal-token-created');
    const value = document.getElementById('personal-token-value');
    const t = JSON.parse(document.getElementById('personal-token-translations').textContent);
    const endpoint = '/user/personal-tokens';
    let reauthToken = '';
    function request(method, url, data) {
        return new Promise((resolve, reject) => $.ajax({type: method, url, contentType: 'application/json',
            data: data === undefined ? undefined : JSON.stringify(data), success: resolve,
            error: xhr => reject(new Error(xhr.responseJSON?.error || t.failed))}));
    }
    function hide() { value.value = ''; created.hidden = true; }
    function time(value) { return value ? new Date(value).toISOString().slice(0, 19).replace('T', ' ') : t.never; }
    async function reload() {
        const data = await request('GET', endpoint);
        table.replaceChildren();
        for (const token of data.tokens) {
            const row = document.createElement('tr');
            const expired = Date.parse(token.expires_at) <= Date.now();
            [token.name, token.group_id, token.scopes.join(', '), time(token.expires_at),
             time(token.last_used_at), token.revoked_at ? t.revoked : expired ? t.expired : !token.available ? t.unavailable : t.active].forEach(text => {
                const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
            });
            const cell = document.createElement('td');
            if (!token.revoked_at && !expired) {
                const button = document.createElement('button'); button.type = 'button'; button.textContent = t.revoke;
                button.addEventListener('click', async () => {
                    if (!window.confirm(t.confirm_revoke)) return;
                    button.disabled = true;
                    try { await request('DELETE', endpoint+'/'+encodeURIComponent(token.id)); hide(); await reload(); status.textContent = t.revoked; }
                    catch (error) { status.textContent = error.message; button.disabled = false; }
                });
                cell.append(button); $(button).button();
            }
            row.append(cell); table.append(row);
        }
    }
    form.addEventListener('submit', async event => {
        event.preventDefault(); hide();
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        const data = {name: form.elements.name.value, group_id: Number(form.dataset.group),
            expires_days: Number(form.elements.expires_days.value), password: form.elements.password.value,
            otp: form.elements.otp.value, reauth_token: reauthToken,
            scopes: [...form.querySelectorAll('[name="scope"]:checked')].map(node => node.value)};
        try {
            const result = await request('POST', endpoint, data);
            value.value = result.access_token; created.hidden = false;
            form.elements.password.value = ''; form.elements.otp.value = ''; reauthToken = '';
            await reload(); status.textContent = t.created;
            created.scrollIntoView({block: 'center'});
        } catch (error) { status.textContent = error.message; }
        finally { button.disabled = false; form.elements.password.value = ''; form.elements.otp.value = ''; data.password = ''; data.otp = ''; data.reauth_token = ''; reauthToken = ''; }
    });
    const passkey = document.getElementById('personal-token-passkey');
    if (passkey && typeof window.roxywiReauthenticate === 'function') {
        passkey.hidden = false;
        passkey.addEventListener('click', async () => {
            try { reauthToken = await window.roxywiReauthenticate('personal_token.create'); status.textContent = t.reauthenticated; }
            catch (error) { status.textContent = error.message; }
        });
    }
    document.getElementById('personal-token-hide').addEventListener('click', () => { hide(); status.textContent = t.hidden; });
    window.addEventListener('pagehide', hide);
    reload().catch(error => { status.textContent = error.message; });
})();
