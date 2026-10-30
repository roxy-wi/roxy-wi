"""Configuration-derived routes remain candidates; unknown routes stay explicit."""
import json

import pytest

from app.modules.service import haproxy, published_endpoints


def front(result, ident):
    return next(value for value in result['frontends'] if value['id']==ident)


def test_listen_keeps_local_servers_and_conditional_backend_dependencies():
    text='''listen public
 bind *:443 ssl
 mode http
 use_backend api if { path_beg /api }
 default_backend fallback
 server local 192.0.2.10:8080
backend api
 server api 192.0.2.11:8081
backend fallback
 server fallback 192.0.2.12:8082
backend unrelated
 server unrelated 192.0.2.99:9090
'''
    graph=haproxy.build_dependency_graph(text)
    edges={(edge['source'],edge['target']) for edge in graph['edges']}
    assert ('listen:public','backend:api') in edges
    assert ('listen:public','backend:fallback') in edges
    result=published_endpoints.parse('haproxy',text)
    selected=front(result,'listen:public')
    assert {backend['host'] for backend in selected['backends']}=={'192.0.2.10','192.0.2.11','192.0.2.12'}
    assert selected['unresolved_routes']==0 and not selected['partial'] and not result['partial']
    assert selected['tls'] and selected['listeners'][0]['port']==443


@pytest.mark.parametrize('section',['frontend','listen'])
@pytest.mark.parametrize('expression',[
    '%[req.hdr(host),map(/private/NeverExposeSecret.map,fallback)]',
    'prefix-%[var(txn.route)]', '$BACKEND_NAME', '"%[var(txn.route)] with space"',
])
def test_dynamic_backend_expressions_are_never_invented_as_nodes_or_exported(section,expression):
    text=f'''{section} public
 bind :443
 use_backend {expression} if site
 default_backend healthy
backend healthy
 server app 192.0.2.10:8080
'''
    graph=haproxy.build_dependency_graph(text)
    assert graph['counts']['backend']==1
    assert [edge['type'] for edge in graph['edges']].count('use_backend')==0
    assert graph['partial']
    result=published_endpoints.parse('haproxy',text);selected=front(result,f'{section}:public')
    assert selected['unresolved_routes']==1 and selected['partial'] and result['partial']
    assert [value['host'] for value in selected['backends']]==['192.0.2.10']
    assert selected['unsupported_backends']==0
    assert selected['unresolved_route_evidence']==[
        dict(directive='use_backend',reason='dynamic-backend-expression',line=3)]
    for secret in ['NeverExposeSecret','$BACKEND_NAME','txn.route','req.hdr','/private/']:
        assert secret not in json.dumps(result)


def test_undefined_backends_stay_compatible_but_do_not_look_fully_inventoried():
    text='''frontend incomplete
 bind :443
 use_backend missing if site
 default_backend later
frontend complete
 bind :8443
 default_backend later
backend later
 server app 192.0.2.10:8080
'''
    graph=haproxy.build_dependency_graph(text)
    assert next(node for node in graph['nodes'] if node['id']=='backend:missing')['defined'] is False
    assert next(node for node in graph['nodes'] if node['id']=='backend:later')['defined'] is True
    result=published_endpoints.parse('haproxy',text)
    assert front(result,'frontend:incomplete')['unresolved_routes']==1
    assert front(result,'frontend:incomplete')['partial']
    assert front(result,'frontend:complete')['unresolved_routes']==0
    assert not front(result,'frontend:complete')['partial']
    assert result['partial']


def test_unresolved_route_count_is_exact_when_evidence_is_bounded():
    text='frontend public\n bind :443\n'+''.join(' use_backend %[var(txn.secret)] if acl\n' for _ in range(40))
    selected=published_endpoints.parse('haproxy',text)['frontends'][0]
    assert selected['unresolved_routes']==40 and len(selected['unresolved_route_evidence'])==16
    assert not selected['backends'] and selected['partial']
    assert 'txn.secret' not in json.dumps(selected)


def test_missing_and_invalid_route_targets_are_explicit():
    text='frontend public\n bind :443\n use_backend\n default_backend invalid/name\n'
    selected=published_endpoints.parse('haproxy',text)['frontends'][0]
    assert selected['unresolved_routes']==2 and selected['partial'] and not selected['backends']
    assert [item['reason'] for item in selected['unresolved_route_evidence']]==[
        'missing-backend-target','invalid-backend-name']


@pytest.mark.parametrize('mode',['v4v6','v6only'])
def test_explicit_ipv6_bind_mode_is_attached_only_to_its_own_listener(mode):
    text=f'''frontend public
 bind [::]:443 {mode} ssl
 bind [::]:8443
 bind 192.0.2.10:9443
'''
    listeners=published_endpoints.parse('haproxy',text)['frontends'][0]['listeners']
    assert listeners[0]['address_family']==mode
    assert 'address_family' not in listeners[1] and 'address_family' not in listeners[2]


def test_conflicting_ipv6_bind_modes_remain_conservatively_ipv6_only():
    text='frontend public\n bind [::]:443 v4v6\n bind [::]:443 v6only\n'
    listeners=published_endpoints.parse('haproxy',text)['frontends'][0]['listeners']
    assert len(listeners)==1 and listeners[0]['address_family']=='v6only'


def test_undefined_nginx_upstream_counts_each_route_without_exporting_target():
    text='http { server { listen 443; location /a { proxy_pass http://missing; } location /b { proxy_pass http://missing; } } }'
    selected=published_endpoints.parse('nginx',text)['frontends'][0]
    assert selected['unresolved_routes']==2 and selected['partial'] and not selected['backends']
    assert len(selected['unresolved_route_evidence'])==2


@pytest.mark.parametrize('service,text',[
    ('nginx','http { server { listen 443; location / { proxy_pass http://$NeverExposeSecret:8080; } } }'),
    ('apache','<VirtualHost *:443>\nProxyPass / http://${NeverExposeSecret}:8080/\n</VirtualHost>'),
])
def test_other_dynamic_backend_authorities_are_partial_and_not_double_counted(service,text):
    result=published_endpoints.parse(service,text);selected=result['frontends'][0]
    assert selected['unresolved_routes']==1 and selected['unsupported_backends']==0
    assert selected['partial'] and result['partial'] and not selected['backends']
    assert 'NeverExposeSecret' not in json.dumps(result)


def test_variable_nginx_request_path_does_not_hide_a_static_backend_destination():
    text='http { server { listen 443; location / { proxy_pass http://192.0.2.10:8080/$request_uri; } } }'
    selected=published_endpoints.parse('nginx',text)['frontends'][0]
    # endpoint() conservatively excludes variable-bearing raw endpoints. Keep
    # that existing bound explicit instead of guessing URI expansion semantics.
    assert selected['unsupported_backends']==1 and selected['partial']
    assert selected['unresolved_routes']==0


@pytest.mark.parametrize('options,expected',[
    ('ssl crt v4v6',None),
    ('ssl crt v6only v4v6','v4v6'),
    ('ssl crt /private/site.pem v6only','v6only'),
    ('name v4v6',None),
    ('unknown-option v4v6',None),
])
def test_bind_option_values_cannot_be_mistaken_for_dual_stack_flags(options,expected):
    listener=published_endpoints.parse('haproxy',f'frontend public\n bind [::]:443 {options}\n')['frontends'][0]['listeners'][0]
    assert listener.get('address_family')==expected


@pytest.mark.parametrize('address',['*:443',':443'])
def test_haproxy_wildcard_and_omitted_bind_address_are_explicitly_ipv4(address):
    text=f'frontend public\n bind {address}\n'
    assert haproxy.build_dependency_graph(text)['nodes'][0]['addresses']==[address]
    listener=published_endpoints.parse('haproxy',text)['frontends'][0]['listeners'][0]
    assert listener['host']=='0.0.0.0' and listener['port']==443


@pytest.mark.parametrize('options',['v4v6 v6only','v6only v4v6'])
def test_v6only_takes_precedence_within_one_bind(options):
    listener=published_endpoints.parse('haproxy',f'frontend public\n bind [::]:443 {options}\n')['frontends'][0]['listeners'][0]
    assert listener['address_family']=='v6only'


@pytest.mark.parametrize('address',['443','*:443'])
def test_nginx_implicit_ipv4_listener_does_not_authorize_ipv6(address):
    result=published_endpoints.parse('nginx',f'http {{ server {{ listen {address}; }} }}')
    assert result['frontends'][0]['listeners'][0]['host']=='0.0.0.0'


def test_apache_virtual_host_wildcard_keeps_its_service_specific_scope():
    result=published_endpoints.parse('apache','<VirtualHost *:443>\nServerName example.test\n</VirtualHost>')
    assert result['frontends'][0]['listeners'][0]['host']=='*'
