from concurrent.futures import ThreadPoolExecutor
import socket
import subprocess
import sys

import pytest

from app.modules.config.candidate import SPOA_HEALTHCHECK


# SPOP 2.0 AGENT-HELLO: FIN, zero stream/frame, version 2.0, maximum frame 128,
# empty capabilities. Fixed wire fixture, independent of the probe encoder.
HELLO = (b'\x65\x00\x00\x00\x01\x00\x00'
         b'\x07version\x08\x032.0\x0emax-frame-size\x03\x80\x0ccapabilities\x08\x00')


@pytest.mark.parametrize('scenario', ['valid', 'fragmented', 'disconnect', 'wrong_version', 'missing_size',
                                     'oversized', 'truncated', 'duplicate', 'invalid_type', 'unbounded_string'])
def test_probe_requires_a_complete_compatible_spop_hello(scenario):
    payload = HELLO
    if scenario == 'disconnect':
        payload = b'\x66' + HELLO[1:]
    elif scenario == 'wrong_version':
        payload = HELLO.replace(b'2.0', b'1.0')
    elif scenario == 'missing_size':
        payload = HELLO.replace(b'\x0emax-frame-size\x03\x80', b'')
    elif scenario == 'oversized':
        payload += b'x' * 128
    elif scenario == 'duplicate':
        payload += b'\x07version\x08\x032.0'
    elif scenario == 'invalid_type':
        payload = HELLO.replace(b'\x03\x80', b'\x08\x00')
    elif scenario == 'unbounded_string':
        payload = HELLO[:-1] + b'\xff'
    frame = len(payload).to_bytes(4, 'big') + payload
    if scenario == 'truncated':
        frame = frame[:-2]

    with socket.socket() as listener, ThreadPoolExecutor(max_workers=1) as executor:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)

        def agent():
            with listener.accept()[0] as connection:
                connection.settimeout(5)
                data = b''
                while len(data) < 4 or len(data) < 4 + int.from_bytes(data[:4], 'big'):
                    part = connection.recv(256)
                    assert part, 'Client closed before sending its HELLO'
                    data += part
                assert data[4:11] == b'\x01\x00\x00\x00\x01\x00\x00'
                assert b'\x12supported-versions\x08\x032.0' in data
                assert b'\x0emax-frame-size\x03\x80' in data
                assert data.endswith(b'\x0bhealthcheck\x11')
                if scenario == 'fragmented':
                    for byte in frame:
                        connection.sendall(bytes([byte]))
                else:
                    connection.sendall(frame)

        future = executor.submit(agent)
        result = subprocess.run([sys.executable, '-c', SPOA_HEALTHCHECK, str(listener.getsockname()[1])],
                                capture_output=True, timeout=5, check=False)
        future.result(timeout=5)
    assert result.returncode == (0 if scenario in ('valid', 'fragmented') else 1)
    assert not result.stdout and not result.stderr
