"""Exercise host charts with real Chart.js and deterministic OS measurements."""
import os

import pytest


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


def open_overview(page, product_url):
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    assert page.goto(product_url + '/overview').status == 200
    page.wait_for_function("Chart.getChart('cpu') && Chart.getChart('ram')")


def test_host_charts_load_once_and_reuse_instances_on_refresh(logged_in, product_url, host_metrics):
    page = logged_in
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    open_overview(page, product_url)
    for metric in ('cpu', 'ram'):
        assert requests.count(product_url + '/metrics/' + metric) == 1
    original_ids = page.evaluate("['cpu', 'ram'].map(id => Chart.getChart(id).id)")
    for value in (25, 40, 15):
        host_metrics['cpu'][0] = value
        host_metrics['ram'][0] = value * 100
        page.locator('a[onclick="showOverviewHapWI()"]').click()
        page.wait_for_function('''value => Chart.getChart('cpu').data.datasets[0].data[0] === value
            && Chart.getChart('ram').data.datasets[0].data[0] === value * 100''', arg=value)
        assert page.evaluate("['cpu', 'ram'].map(id => Chart.getChart(id).id)") == original_ids
        assert page.evaluate('Object.keys(Chart.instances).length') == 2
        assert page.evaluate('charts.length') == 2
    # A failed refresh preserves the last readings; the next refresh recovers.
    page.route('**/metrics/ram', lambda route: route.fulfill(status=503, json={'error': 'Temporary metrics failure'}))
    with page.expect_response(lambda response: response.url.endswith('/metrics/ram')):
        page.locator('a[onclick="showOverviewHapWI()"]').click()
    assert page.evaluate("Chart.getChart('ram').data.datasets[0].data[0]") == 1500
    page.unroute('**/metrics/ram')
    host_metrics['ram'][0] = 1200
    page.locator('a[onclick="showOverviewHapWI()"]').click()
    page.wait_for_function("Chart.getChart('ram').data.datasets[0].data[0] === 1200")
    assert page.evaluate("['cpu', 'ram'].map(id => Chart.getChart(id).id)") == original_ids


def test_late_host_metrics_do_not_overwrite_newer_data_or_replaced_canvas(logged_in, product_url, host_metrics):
    page = logged_in
    open_overview(page, product_url)
    result = page.evaluate('''() => {
        const ajax = $.ajax;
        const pending = [];
        $.ajax = options => { pending.push(options); return {abort() {}}; };
        try {
            getChartDataHapWiRam('192.0.2.1');
            getChartDataHapWiRam('192.0.2.2');
            pending[1].success({chartData: {rams: '200 20 3 4 5 6'}});
            pending[0].success({chartData: {rams: '100 10 3 4 5 6'}});
            const ram = Chart.getChart('ram').data.datasets[0].data[0];
            getChartDataHapWiCpu('192.0.2.1');
            getChartDataHapWiCpu('192.0.2.2');
            pending[3].success({chartData: {cpus: '20 5 0 80 2 1 2 0 20'}});
            pending[2].success({chartData: {cpus: '10 5 0 80 2 1 2 0 20'}});
            const cpu = Chart.getChart('cpu').data.datasets[0].data[0];
            getChartDataHapWiRam('192.0.2.3');
            const oldCanvas = document.getElementById('ram');
            const replacement = document.createElement('canvas');
            replacement.id = 'ram';
            Chart.getChart(oldCanvas).destroy();
            oldCanvas.replaceWith(replacement);
            pending[4].success({chartData: {rams: '999 20 3 4 5 6'}});
            return {ram, cpu, replacementHasChart: Boolean(Chart.getChart(replacement))};
        } finally { $.ajax = ajax; }
    }''')
    assert result == {'ram': 200, 'cpu': 20, 'replacementHasChart': False}
