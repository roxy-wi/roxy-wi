/* Deployment evidence is part of the existing certificate operation, not a monitor. */
window.certificateVerification = report => {
    if (!report) return null;
    const labels = JSON.parse(document.getElementById('certificate-verification-strings').textContent);
    const node = (tag, text) => {
        const item = document.createElement(tag);
        if (text) item.textContent = text;
        return item;
    };
    const detail = node('details');
    detail.className = 'rw-form-field';
    detail.dataset.certificateVerification = report.state;
    detail.style.overflowWrap = 'anywhere';
    detail.append(node('summary', labels.title + ': ' + (labels[report.state] || report.state)));
    detail.append(node('p', labels.observed + ': ' + new Date(report.observed_at).toLocaleString()));
    detail.append(node('p', labels.expected + ': SHA-256 ' + report.expected_fingerprint));
    const list = node('ul');
    for (const endpoint of report.endpoints || []) {
        const item = node('li', [endpoint.address, endpoint.domain,
            endpoint.port ? ':' + endpoint.port : '', labels[endpoint.state] || endpoint.state].filter(Boolean).join(' · '));
        if (endpoint.fingerprint) item.append(node('p', labels.actual + ': SHA-256 ' + endpoint.fingerprint));
        list.append(item);
    }
    detail.append(list, node('p', labels.scope));
    return detail;
};
