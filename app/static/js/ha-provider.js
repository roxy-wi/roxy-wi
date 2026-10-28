jQuery(() => {
    const select = document.getElementById('ha-provider');
    if (!select) return;
    jQuery(select).on('selectmenuchange change', () => {
        const option = select.selectedOptions[0];
        if (!option || option.disabled || !option.dataset.url) return;
        let url;
        try {
            url = new URL(option.dataset.url, window.location.origin);
        } catch {
            return;
        }
        // Generated navigation targets must stay on this HTTP(S) application.
        if (!['http:', 'https:'].includes(url.protocol) || url.origin !== window.location.origin) return;
        window.location.assign(url.href);
    });
});
