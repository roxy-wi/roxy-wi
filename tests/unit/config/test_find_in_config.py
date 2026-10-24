from app.modules.config import config as config_mod


HIGHLIGHT = '<span style="color: red; font-weight: bold;">{}</span>'


def test_find_in_config_keeps_line_text_intact():
    stdout = [
        '/etc/haproxy/haproxy.cfg-11-frontend http_front',
        '/etc/haproxy/haproxy.cfg:12:    bind *:80,*:8080',
        '/etc/haproxy/haproxy.cfg-13-    acl is_api path_beg -i /api',
    ]
    out = config_mod.show_finding_in_config(stdout, grep='bind *:80')

    assert '    ' + HIGHLIGHT.format('bind *:80') + ',*:8080' in out
    assert 'frontend http_front' in out
    assert 'acl is_api path_beg -i /api' in out


def test_find_in_config_escapes_html_in_lines_and_search_word():
    stdout = ['/etc/nginx/nginx.conf:3:    return 200 "<b>ok</b> & more";']
    out = config_mod.show_finding_in_config(stdout, grep='<b>ok</b> &')

    assert '<b>' not in out.replace(HIGHLIGHT.format('&lt;b&gt;ok&lt;/b&gt; &amp;'), '')
    assert HIGHLIGHT.format('&lt;b&gt;ok&lt;/b&gt; &amp;') + ' more' in out
