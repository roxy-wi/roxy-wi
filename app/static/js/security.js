/* Persistent local authentication; credentials and one-use proofs stay in memory. */
(function () {
    'use strict';
    function request(url, method, data) {
        return $.ajax({url: url, type: method, contentType: 'application/json', headers: {'X-CSRF-TOKEN': Cookies.get('csrf_access_token') || ''}, data: data ? JSON.stringify(data) : undefined});
    }
    window.roxywiSecurityRequest = request;
    window.roxywiSecurityCodes = function (codes, finished) {
        const dialog = $('<div class="security-recovery-dialog">');
        $('<p>').text('Save these recovery codes now. They are shown once and each code works once.').appendTo(dialog);
        $('<pre class="security-recovery">').text(codes.join('\n')).appendTo(dialog);
        dialog.dialog({title: 'Recovery codes', modal: true, width: Math.min(570, window.innerWidth - 24),
            close: function () {dialog.remove(); if (finished) finished();},
            buttons: [{text: 'I saved my recovery codes', click: function () {dialog.dialog('close');}}]});
    };
    window.roxywiReauthenticate = function (purpose) {
        return new Promise(function (resolve, reject) {
            request('/auth/security', 'GET').then(function (status) {
                let done = false;
                const dialog = $('<form class="security-reauth">');
                const password = $('<input type="password" autocomplete="current-password" required>').attr('id', 'reauth-password');
                $('<label for="reauth-password">').text('Current password').appendTo(dialog); password.appendTo(dialog);
                const otp = $('<input autocomplete="one-time-code">').attr('id', 'reauth-code');
                if (status.factors.length) {
                    $('<label for="reauth-code">').text('Authenticator or recovery code').appendTo(dialog); otp.appendTo(dialog);
                }
                const error = $('<p role="alert" class="security-error">').appendTo(dialog);
                function finish(token) {done = true; dialog.dialog('close'); resolve(token);}
                function failed(xhr) {error.text(xhr.responseJSON?.error || 'Authentication failed. Check your credentials and try again.'); password.val(''); otp.val('');}
                function submit(event) {
                    if (event) event.preventDefault();
                    const value = String(otp.val() || '').trim();
                    const data = {purpose: purpose, password: password.val()};
                    data[value.replace(/-/g, '').length === 32 ? 'recovery_code' : 'otp'] = value;
                    request('/auth/reauthenticate', 'POST', data).then(result => finish(result.reauth_token), failed);
                }
                dialog.on('submit', submit);
                const buttons = [{text: 'Verify', click: submit}, {text: 'Cancel', click: () => dialog.dialog('close')}];
                if (typeof window.roxywiPasskeyReauthenticate === 'function' && status.factors.includes('passkeys')) {
                    buttons.unshift({text: 'Use passkey', click: () => window.roxywiPasskeyReauthenticate(purpose).then(finish, failed)});
                }
                dialog.dialog({title: 'Verify your identity', modal: true, width: Math.min(440, window.innerWidth - 24), buttons: buttons,
                    close: function () {password.val(''); otp.val(''); dialog.remove(); if (!done) reject(new Error('Authentication cancelled'));}});
            }, reject);
        });
    };
    window.roxywiLocalLogin = function (initial) {
        $('#pass').val('');
        $('#auth').hide();
        $('#local-auth-step').remove();
        const step = $('<div id="local-auth-step">').appendTo('.login-auth-column');
        const message = $('<p role="status">').appendTo(step);
        const error = $('<p role="alert" class="security-error">').appendTo(step);
        function failed(xhr) {error.text(xhr.responseJSON?.error || 'Authentication failed. Start again if the request expired.');}
        function complete(result) {
            const proceed = () => {sessionStorage.removeItem('check-service'); window.location.replace(result.next_url);};
            if (result.recovery_codes) window.roxywiSecurityCodes(result.recovery_codes, proceed); else proceed();
        }
        if (initial.status === 'enrollment_required') {
            message.text('Your administrator requires an authenticator. Set it up to continue.');
            const totp = typeof window.roxywiTotpEnrollment === 'function';
            const passkey = typeof window.roxywiPasskeyEnrollment === 'function';
            if (totp && passkey) {
                const choices = $('<div>').appendTo(step);
                $('<button type="button">').text('Set up authenticator').appendTo(choices).on('click', function () {choices.remove(); window.roxywiTotpEnrollment(initial, step, complete, failed);});
                $('<button type="button">').text('Set up passkey').appendTo(choices).on('click', function () {choices.remove(); window.roxywiPasskeyEnrollment(initial, step, complete, failed);});
            } else if (totp) window.roxywiTotpEnrollment(initial, step, complete, failed);
            else if (passkey) window.roxywiPasskeyEnrollment(initial, step, complete, failed);
            return;
        }
        message.text('Enter your authenticator code or a single-use recovery code.');
        const form = $('<form>');
        const input = $('<input id="login-verification-code" autocomplete="one-time-code" aria-label="Authenticator or recovery code" required>').appendTo(form);
        $('<button type="submit">').text('Verify and sign in').appendTo(form);
        form.on('submit', function (event) {
            event.preventDefault(); const value = String(input.val()).trim();
            const data = {challenge: initial.challenge};
            data[value.replace(/-/g, '').length === 32 ? 'recovery_code' : 'otp'] = value;
            request('/auth/login/complete', 'POST', data).then(complete, failed); input.val('');
        });
        if (initial.methods.includes('totp')) form.appendTo(step);
        if (typeof window.roxywiPasskeyContinueLogin === 'function' && initial.methods.includes('passkeys')) {
            $('<button type="button">').text('Use passkey').appendTo(step).on('click', () => window.roxywiPasskeyContinueLogin(initial).then(complete, failed));
            if (!initial.methods.includes('totp')) form.appendTo(step); // Recovery remains available.
        }
        $('<a href="/login">').text('Start again').appendTo(step).css({display:'block', marginTop:'16px'});
        input.trigger('focus');
    };
    $(function () {
        if (!$('#account-security').length) return;
        request('/auth/security', 'GET').then(function (status) {
            $('#recovery-count').text(status.recovery_remaining + ' unused recovery codes');
            $('#regenerate-recovery').prop('disabled', !status.factors.length);
            $('#security-policy').prop('hidden', !status.admin || status.enrollment_required);
            if (status.enrollment_required) $('#security-feedback').text('Your administrator requires MFA. Complete setup to continue.'); $('#mfa-policy').val(status.policy);
        });
        function feedback(error) {if (error?.message === 'Authentication cancelled') return; $('#security-feedback').text(error.responseJSON?.error || error.message || 'Request failed');}
        $('#regenerate-recovery').on('click', () => window.roxywiReauthenticate('recovery.regenerate').then(token => request('/auth/recovery-codes', 'POST', {reauth_token:token})).then(data => {window.roxywiSecurityCodes(data.recovery_codes); $('#recovery-count').text('10 unused recovery codes');}, feedback));
        $('#save-mfa-policy').on('click', () => window.roxywiReauthenticate('policy.update').then(token => request('/auth/policy', 'POST', {reauth_token:token, mode:$('#mfa-policy').val(), grace_days:$('#mfa-grace').val()})).then(() => {window.location='/login';}, feedback));
    });
}());
