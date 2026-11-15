"""Shared harness for the API test suite.

Every test file builds a real Lcore app exposing the feature's endpoints and
probes it two ways:
  * `client`  – in-process TestClient (fast, deterministic)
  * `live`    – a real wsgiref server on an ephemeral port, driven with
                http.client / raw sockets (framing, chunking, keep-alive,
                malformed requests: things TestClient cannot see)
"""
import http.client, os, socket, sys, threading, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import lcore
from lcore import Lcore, TestClient

warnings.filterwarnings('ignore')


class Live:
    """A running server. `.request(...)` returns (status, headers_dict, body)."""

    def __init__(self, app):
        from wsgiref.simple_server import make_server, WSGIRequestHandler

        class Quiet(WSGIRequestHandler):
            def log_message(self, *a): pass

        self.srv = make_server('127.0.0.1', 0, app, handler_class=Quiet)
        self.port = self.srv.server_port
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        data = r.read()
        out = (r.status, {k.lower(): v for k, v in r.getheaders()}, data)
        c.close()
        return out

    def raw(self, payload: bytes, read=65536):
        """Send raw bytes, return whatever the server answers (b'' if it hangs up)."""
        s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        s.sendall(payload)
        try:
            data = s.recv(read)
        except socket.timeout:
            data = b'<timeout>'
        s.close()
        return data

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


@pytest.fixture
def live():
    made = []

    def make(app):
        lv = Live(app); made.append(lv); return lv

    yield make
    for lv in made: lv.close()


@pytest.fixture
def client():
    return lambda app, **kw: TestClient(app, **kw)
