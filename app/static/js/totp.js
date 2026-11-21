(function () {
    'use strict';
    const request = window.roxywiSecurityRequest;
    function setup(container, data, submit) {
        container.find('img').attr('src', data.qr);
        container.find('[data-setup-secret]').val(data.secret);
        container.find('form').off('submit').on('submit', function (event) {event.preventDefault(); submit(container.find('[data-setup-code]').val());});
    }
    window.roxywiTotpEnrollment = function (initial, step, complete, failed) {
        request('/auth/enrollment/start', 'POST', {challenge:initial.challenge}).then(function (data) {
            const panel=$('<div><img alt="Authenticator setup QR code"><label>Setup key<input data-setup-secret readonly></label><form><label>Verification code<input data-setup-code autocomplete="one-time-code" inputmode="numeric" maxlength="6" required></label><button type="submit">Confirm authenticator</button></form></div>').appendTo(step);
            setup(panel,data,code => request('/auth/enrollment/confirm','POST',{challenge:data.challenge,otp:code}).then(complete,failed));
        },failed);
    };
    $(function () {
        if (!$('#account-security').length) return;
        let challenge = '';
        function feedback(error) {if (error?.message === 'Authentication cancelled') return; $('#security-feedback').text(error.responseJSON?.error || error.message || 'Request failed');}
        function clear() {challenge=''; $('#totp-setup').prop('hidden',true); $('#totp-qr').removeAttr('src'); $('#totp-secret,#totp-confirm-code').val('');}
        request('/auth/security','GET').then(function (status) {
            $('#totp-status').text(status.totp ? 'Authenticator enabled' : 'Authenticator not configured');
            $('#setup-totp').text(status.totp ? 'Replace authenticator' : 'Set up authenticator'); $('#remove-totp').prop('hidden',!status.totp);
        });
        $('#setup-totp').on('click',()=>window.roxywiReauthenticate('totp.setup').then(token=>request('/auth/totp/setup','POST',{reauth_token:token})).then(function (data) {
            challenge=data.challenge; $('#totp-qr').attr('src',data.qr); $('#totp-secret').val(data.secret); $('#totp-setup').prop('hidden',false); $('#totp-confirm-code').trigger('focus');
        },feedback));
        $('#cancel-totp').on('click',clear);
        $('#totp-confirm-form').on('submit',function (event) {
            event.preventDefault(); request('/auth/totp/confirm','POST',{challenge:challenge,otp:$('#totp-confirm-code').val()}).then(function (data) {
                clear(); $('#totp-status').text('Authenticator enabled'); $('#setup-totp').text('Replace authenticator'); $('#remove-totp').prop('hidden',false);
                $('#regenerate-recovery').prop('disabled',false); $('#recovery-count').text('10 unused recovery codes');
                window.roxywiSecurityCodes(data.recovery_codes);
            },feedback); $('#totp-confirm-code').val('');
        });
        $('#remove-totp').on('click',()=>window.roxywiReauthenticate('totp.remove').then(token=>request('/auth/totp','DELETE',{reauth_token:token})).then(()=>{window.location='/login';},feedback));
    });
}());
