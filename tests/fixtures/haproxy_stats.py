"""Synthetic HAProxy wire responses shared by Stats product and browser tests."""
import csv
import io


INFO = ('Name: HAProxy\nVersion: 3.0.8\nPid: 100\nProcess_num: 1\nUptime_sec: 3600\n'
        'CurrConns: 7\nMaxconn: 2000\nConnRate: 3\n')
FIELDS = ('pxname svname type pid iid sid status scur slim rate req_rate qcur bin bout '
          'ereq econ eresp weight bck mode addr check_status check_code check_duration '
          'last_chk hrsp_2xx hrsp_5xx qtime ctime rtime ttime lastchg downtime stot').split()
# Static and module columns emitted by HAProxy 2.8 (HTTP/1, HTTP/2 and SSL enabled).
FIELDS_28 = '''
pxname svname qcur qmax scur smax slim stot bin bout dreq dresp ereq econ eresp
wretr wredis status weight act bck chkfail chkdown lastchg downtime qlimit pid iid
sid throttle lbtot tracked type rate rate_lim rate_max check_status check_code
check_duration hrsp_1xx hrsp_2xx hrsp_3xx hrsp_4xx hrsp_5xx hrsp_other hanafail
req_rate req_rate_max req_tot cli_abrt srv_abrt comp_in comp_out comp_byp comp_rsp
lastsess last_chk last_agt qtime ctime rtime ttime agent_status agent_code
agent_duration check_desc agent_desc check_rise check_fall check_health agent_rise
agent_fall agent_health addr cookie mode algo conn_rate conn_rate_max conn_tot
intercepted dcon dses wrew connect reuse cache_lookups cache_hits srv_icur src_ilim
qtime_max ctime_max rtime_max ttime_max eint idle_conn_cur safe_conn_cur used_conn_cur
need_conn_est uweight agg_server_status agg_server_check_status agg_check_status
srid sess_other h1sess h2sess h3sess req_other h1req h2req h3req proto -
h1_open_connections h1_total_connections h1_open_streams h1_total_streams
h1_bytes_in h1_bytes_out h1_spliced_bytes_in h1_spliced_bytes_out h2_headers_rcvd
h2_data_rcvd h2_settings_rcvd h2_rst_stream_rcvd h2_goaway_rcvd
h2_detected_conn_protocol_errors h2_detected_strm_protocol_errors h2_rst_stream_resp
h2_goaway_resp h2_open_connections h2_backend_open_streams h2_total_connections
h2_backend_total_streams ssl_sess ssl_reused_sess ssl_failed_handshake
'''.split()
ROWS = [
    dict(pxname='public', svname='FRONTEND', type=0, iid=2, sid=0, status='OPEN',
         scur=7, slim=2000, rate=3, req_rate=4, mode='http', hrsp_2xx=500, hrsp_5xx=0),
    dict(pxname='web', svname='one', type=2, iid=3, sid=1, status='UP',
         scur=5, slim=100, rate=2, qcur=0, weight=100, bck=0, mode='http',
         addr='192.0.2.30:8080', check_status='L7OK', check_code=200, check_duration=2,
         last_chk='HTTP check passed', rtime=10, downtime=0),
    dict(pxname='web', svname='two', type=2, iid=3, sid=2, status='DOWN',
         scur=0, slim=100, rate=0, qcur=0, weight=50, bck=1, mode='http',
         addr='[2001:db8::30]:8080', check_status='L4CON', last_chk='Connection refused'),
    dict(pxname='web', svname='BACKEND', type=1, iid=3, sid=0, status='UP', scur=5, mode='http'),
    dict(pxname='database', svname='primary', type=2, iid=4, sid=1, status='no check',
         scur=2, mode='tcp', addr='db.example.com:5432'),
]


def stats_csv(rows=None, fields=None):
    fields = fields or FIELDS
    output = io.StringIO(newline='')
    output.write('# ')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow([*fields, ''])
    for row in ROWS if rows is None else rows:
        row = {'pid': 1, 'bin': 1024, 'bout': 2048, 'stot': 100, **row}
        writer.writerow([row.get(field, '') for field in fields] + [''])
    return output.getvalue()
