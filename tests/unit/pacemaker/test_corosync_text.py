import pytest
from app.modules.pacemaker.corosync_text import scalar


def test_replaces_only_witness_host_and_preserves_custom_transport_and_comments():
    text='# host: untouched\ntotem { transport: knet }\nquorum { device { net { # client\n host: "192.0.2.1" # preserve\n tls: required\n } } }\nlogging { to_syslog: yes }\n'
    result=scalar(text,('quorum','device','net','host'),'2001:db8::2')
    assert result==text.replace('"192.0.2.1"','2001:db8::2')
    assert scalar(result,('quorum','device','net','host'))=='2001:db8::2'


@pytest.mark.parametrize('text',['quorum { device { net { host: a host: b } } }','quorum { device { net { host: a } }','host: x'])
def test_duplicate_or_missing_or_unbalanced_configuration_is_refused(text):
    with pytest.raises(ValueError):scalar(text,('quorum','device','net','host'),'192.0.2.2')


def test_optional_scalar_does_not_hide_duplicates_and_reads_same_line_keys():
    assert scalar('totem { keyfile: /private/key }',('totem','keyfile'),optional=True)=='/private/key'
    assert scalar('totem { transport: knet }',('totem','keyfile'),optional=True) is None
    with pytest.raises(ValueError):scalar('totem { keyfile: a keyfile: b }',('totem','keyfile'),optional=True)
