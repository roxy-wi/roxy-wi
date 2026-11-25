/* WebAuthn browser adapter. Credentials and challenges never enter local storage. */
(() => {
    'use strict';
    const decode = value => Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    const encode = value => btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const csrf = () => document.cookie.split('; ').find(v => v.startsWith('csrf_access_token='))?.split('=')[1] || '';
    async function post(path, data) {
        const response = await fetch('/security/passkeys' + path, {method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf()}, body: JSON.stringify(data)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Passkey request failed');
        return result;
    }
    function options(value) {
        const result = {...value, challenge: decode(value.challenge)};
        if (result.user) result.user = {...result.user, id: decode(result.user.id)};
        for (const field of ['allowCredentials', 'excludeCredentials']) {
            if (result[field]) result[field] = result[field].map(c => ({...c, id: decode(c.id)}));
        }
        return result;
    }
    function serialize(credential) {
        const response = {};
        for (const field of ['clientDataJSON', 'attestationObject', 'authenticatorData', 'signature', 'userHandle']) {
            if (credential.response[field] != null) response[field] = encode(credential.response[field]);
        }
        return {id: credential.id, rawId: encode(credential.rawId), type: credential.type, response,
                authenticatorAttachment: credential.authenticatorAttachment,
                clientExtensionResults: credential.getClientExtensionResults()};
    }
    async function assertion(begin, data) {
        if (!window.PublicKeyCredential) throw new Error('This browser does not support passkeys');
        const start = await post(begin, data);
        const credential = await navigator.credentials.get({publicKey: options(start.publicKey)});
        if (!credential) throw new Error('Passkey authentication was cancelled');
        return {...start, credential: serialize(credential)};
    }
    window.roxywiPasskeyReauthenticate = async purpose => {
        const proof = await assertion('/reauth/options', {purpose});
        const result = await post('/reauth/finish', {purpose, challenge_token: proof.challenge_token, credential: proof.credential});
        return result.reauth_token;
    };
    window.roxywiPasskeyFactor = async (challenge, purpose = 'login:web') => {
        const proof = await assertion('/factor/options', {login_challenge: challenge, purpose});
        return {challenge: proof.login_challenge, passkey_challenge: proof.challenge_token, credential: proof.credential};
    };
    window.roxywiPasskeyContinueLogin = async data => {
        if (data.status === 'enrollment_required') {
            const name = window.prompt('Name this passkey (for example: work laptop)');
            if (!name) throw new Error('A passkey name is required');
            const start = await post('/enrollment/options', {challenge: data.challenge});
            const credential = await navigator.credentials.create({publicKey: options(start.publicKey)});
            return post('/enrollment/finish', {name, challenge_token: start.challenge_token, credential: serialize(credential)});
        }
        const proof = await window.roxywiPasskeyFactor(data.challenge);
        const response = await fetch('/auth/login/complete', {method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(proof)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Passkey sign in failed');
        return result;
    };
    window.roxywiPasskeyEnrollment = (initial, step, complete, failed) => {
        $('<button type="button">').text('Set up a passkey').appendTo(step).on('click', event => {
            const button = event.currentTarget; button.disabled = true;
            window.roxywiPasskeyContinueLogin(initial).then(complete, failed).finally(() => {button.disabled = false;});
        });
    };
    function show(message) {
        const element = document.getElementById('passkey-status');
        if (element) element.textContent = message;
    }
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('passkey-login')?.addEventListener('click', async event => {
            const button = event.currentTarget; button.disabled = true;
            try {
                const proof = await assertion('/login/options', {login: document.getElementById('login').value});
                const result = await post('/login/finish', {challenge_token: proof.challenge_token,
                    credential: proof.credential, next: new URLSearchParams(location.search).get('next') || ''});
                location.assign(result.next_url);
            } catch (error) { show(error.message); }
            finally { button.disabled = false; }
        });
        document.getElementById('passkey-add')?.addEventListener('click', async event => {
            const button = event.currentTarget; button.disabled = true;
            try {
                const name = document.getElementById('passkey-name').value.trim();
                if (!name) throw new Error('Enter a passkey name');
                const proof = await window.roxywiReauthenticate('passkeys.register');
                const start = await post('/register/options', {reauth_token: proof});
                const credential = await navigator.credentials.create({publicKey: options(start.publicKey)});
                const result = await post('/register/finish', {name, challenge_token: start.challenge_token, credential: serialize(credential)});
                if (result.recovery_codes?.length) {
                    document.getElementById('passkey-recovery').hidden = false;
                    document.getElementById('passkey-recovery-codes').textContent = result.recovery_codes.join('\n');
                    show('Passkey added. Save your recovery codes before continuing.');
                } else location.reload();
            } catch (error) { show(error.message); }
            finally { button.disabled = false; }
        });
        document.querySelectorAll('[data-passkey-remove]').forEach(button => button.addEventListener('click', async () => {
            button.disabled = true;
            try {
                const proof = await window.roxywiReauthenticate('passkeys.remove');
                await post('/' + button.dataset.passkeyRemove + '/remove', {reauth_token: proof});
                location.assign('/login');
            } catch (error) { show(error.message); }
            finally { button.disabled = false; }
        }));
    });
})();
